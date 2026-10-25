// SPDX-License-Identifier: MIT
/*
 * Minimal boot progress observer for the ishtar bring-up.
 *
 * kits/sheng/BootProgress.c is a full monitor: it reads the counters of the UFS, Virtio block,
 * ADSP, touch, GPU and cpufreq components directly, and only three of those reads are weak.
 * Linking it therefore needs every one of those components built; on a reduced config the link
 * stops on 118 undefined symbols, which is why CONFIG_XNU_BOOT_PROGRESS has always been off.
 *
 * This file implements the same thirteen entry points that zzz-boot-progress.patch calls, with
 * no dependency outside the kernel image. It draws into the frame buffer video_console already
 * mapped and keeps the history in static storage, so it links into any config.
 *
 * Design rules, in order of importance:
 *   1. Never fault. Every pointer that comes from the kernel is probe-translated with AT S1E1R
 *      before it is read, and every frame buffer store is bounded by the geometry the console
 *      reported. A diagnostic that faults turns a hang into a hang with no output.
 *   2. Never write more pixels than needed. One completed log line repaints one row band; the
 *      panel repaints only when its text or colour actually changes.
 *   3. Never swallow the console unless there is a screen to put it on: boot_progress_active()
 *      stays false until a frame buffer has been validated, so a machine where the bind fails
 *      boots exactly as it does today.
 */
#include <stdint.h>
#include <stddef.h>

#include "Font.h"                       /* GLYPH_FONT: 96 glyphs, 5x12, packed in a uint64_t */

/* Text buffer width. The visible column count comes from the panel geometry and is clamped to
 * this; 60 columns is what a 1440x3200 panel gives at scale 4. */
#define BP_MAX_COLS     79
#define BP_MAX_ROWS     64
/* Twenty rows were not enough: a burst of console output evicted the pre-bind stages, which are
 * the ones that cannot be recovered any other way. Forty rows cost nothing extra per line - a
 * completed line still repaints one row band - and they fit a 1440x3200 panel at scale 4 (49 of
 * the 57 available rows). */
#define BP_LOG_LINES    40
#define BP_PANEL_LINES   6

/* Colours, 0x00RRGGBB. */
#define BP_BLACK   0x00000000u
#define BP_WHITE   0x00FFFFFFu
#define BP_GREY    0x00C8C8C8u
#define BP_AMBER   0x00FFC000u
#define BP_GREEN   0x0040FF80u
#define BP_RED     0x00FF5050u
#define BP_BLUE    0x0060B0FFu
#define BP_INK     0x00101010u

/* AT S1E1R with PAR_EL1.F clear means the current translation regime maps the address. It is a
 * hardware query only: no table edit, no mapping, no exception. Used here for the same reason
 * the panic screen uses it - the frame buffer's physical address is a kernel virtual address
 * only while the bootstrap identity map sits in TTBR0, and heap strings are not always mapped. */
static int
bp_translated(uintptr_t address)
{
#if defined(__aarch64__)
	uint64_t par;

	__asm__ volatile ("at s1e1r, %1; isb; mrs %0, par_el1" : "=r" (par) : "r" (address) : "memory");
	return (par & 1u) == 0;
#else
	(void) address;
	return 1;
#endif
}

/* Kernel virtual addresses only, and only when the page is actually present. */
static int
bp_readable(const void *pointer)
{
	uintptr_t address = (uintptr_t) pointer;

	if (address < 0xffff000000000000ull) {
		return 0;
	}
	return bp_translated(address);
}

/* arm_vm_init() installs the physical aperture; until then the variable is zero. Reading it is
 * always safe - it lives in the kernel image - so this needs no probe. */
extern const uint64_t physmap_base;

static const uint64_t bp_font[] = GLYPH_FONT;

static struct {
	volatile uint32_t *fb;
	unsigned width;                 /* pixels */
	unsigned height;                /* pixels */
	unsigned stride;                /* bytes per scan line */
	unsigned scale;
	unsigned cols;
	unsigned rows;
	unsigned bound;                 /* frame buffer validated, rendering allowed */
	unsigned painted;               /* at least one full flush has happened */
	char     model[BP_MAX_ROWS][BP_MAX_COLS + 1];
	uint32_t model_fg[BP_MAX_ROWS];
	uint32_t model_bg[BP_MAX_ROWS];
	char     shown[BP_MAX_ROWS][BP_MAX_COLS + 1];
	uint32_t shown_fg[BP_MAX_ROWS];
	uint32_t shown_bg[BP_MAX_ROWS];
} g_screen;

static struct {
	unsigned initialized;
	unsigned start_seen;
	unsigned stages;
	unsigned long long irqs;
	unsigned long long faults;
	unsigned long long breakpoints;
	char     log[BP_LOG_LINES][BP_MAX_COLS + 1];
	unsigned log_number[BP_LOG_LINES];
	unsigned log_row;               /* slot the next character goes into */
	unsigned log_count;             /* lines completed, also the number of the current line */
	unsigned line_dirty;            /* the current slot holds at least one character */
	char     last[BP_MAX_COLS + 1];
	char     process[BP_MAX_COLS + 1];
	char     brk[BP_MAX_COLS + 1];
	char     abort_line[BP_MAX_COLS + 1];
	char     exit_line[BP_MAX_COLS + 1];
	char     critical[BP_MAX_COLS + 1];
} g_state;

/* ---------------------------------------------------------------- bounded string and number I/O */

static void
bp_copy(char *destination, const char *source)
{
	unsigned index = 0;

	if (source != NULL) {
		while (index < BP_MAX_COLS && source[index] != 0) {
			destination[index] = source[index];
			index++;
		}
	}
	while (index <= BP_MAX_COLS) {
		destination[index++] = 0;
	}
}

/* Copy at most limit bytes of a string the kernel handed us, after proving the first page is
 * mapped. Process names live in the proc structure, not in the linked image. */
static void
bp_copy_probed(char *destination, const char *source, unsigned limit)
{
	unsigned index = 0;

	if (limit > BP_MAX_COLS) {
		limit = BP_MAX_COLS;
	}
	if (source == NULL || !bp_readable(source)) {
		while (index <= BP_MAX_COLS) {
			destination[index++] = 0;
		}
		return;
	}
	while (index < limit && source[index] != 0) {
		destination[index] = source[index];
		index++;
	}
	while (index <= BP_MAX_COLS) {
		destination[index++] = 0;
	}
}

struct bp_out {
	char *text;
	unsigned used;
};

static void
bp_out_puts(struct bp_out *out, const char *text)
{
	while (text != NULL && *text != 0 && out->used < BP_MAX_COLS) {
		out->text[out->used++] = *text++;
	}
	out->text[out->used] = 0;
}

static void
bp_out_dec(struct bp_out *out, uint64_t value)
{
	char digits[24];
	unsigned count = 0;

	do {
		digits[count++] = (char) ('0' + (value % 10u));
		value /= 10u;
	} while (value != 0 && count < sizeof(digits));
	while (count != 0) {
		if (out->used < BP_MAX_COLS) {
			out->text[out->used++] = digits[--count];
		} else {
			count--;
		}
	}
	out->text[out->used] = 0;
}

static void
bp_out_hex(struct bp_out *out, uint64_t value, unsigned digits)
{
	static const char hex[] = "0123456789abcdef";
	unsigned index;

	for (index = 0; index < digits; index++) {
		if (out->used < BP_MAX_COLS) {
			out->text[out->used++] = hex[(value >> ((digits - 1u - index) * 4u)) & 0xfu];
		}
	}
	out->text[out->used] = 0;
}

static void
bp_out_begin(struct bp_out *out, char *buffer)
{
	out->text = buffer;
	out->used = 0;
	buffer[0] = 0;
}

/* ---------------------------------------------------------------------------- frame buffer paint */

static void
bp_pixel(unsigned x, unsigned y, uint32_t colour)
{
	g_screen.fb[(y * (g_screen.stride >> 2)) + x] = colour;
}

/* One character cell. The font packs twelve scan lines into a uint64_t: rows 0..5 in the high
 * word, rows 6..11 in the low word, five bits each, most significant bit leftmost. The cell is
 * 6x14 cells-of-8 so there is a blank column and two blank scan lines of letter spacing. */
static void
bp_cell(unsigned row, unsigned column, char character, uint32_t fg, uint32_t bg)
{
	const unsigned scale = g_screen.scale;
	unsigned x0 = column * 6u * scale;
	unsigned y0 = row * 14u * scale;
	uint64_t glyph;
	unsigned y, dx, sy, sx;

	if (x0 + 6u * scale > g_screen.width || y0 + 14u * scale > g_screen.height) {
		return;
	}
	if (character < 32 || character > 126) {
		character = '?';
	}
	glyph = bp_font[(unsigned) character - 32u];
	for (y = 0; y < 14; y++) {
		unsigned bits = 0;

		if (y < 6) {
			bits = (unsigned) ((glyph >> (32u + y * 5u)) & 0x1fu);
		} else if (y < 12) {
			bits = (unsigned) ((glyph >> ((y - 6u) * 5u)) & 0x1fu);
		}
		for (dx = 0; dx < 6; dx++) {
			uint32_t colour = (dx < 5 && ((bits >> dx) & 1u) != 0) ? fg : bg;

			for (sy = 0; sy < scale; sy++) {
				for (sx = 0; sx < scale; sx++) {
					bp_pixel(x0 + dx * scale + sx, y0 + y * scale + sy, colour);
				}
			}
		}
	}
}

static void
bp_model_row(unsigned row, const char *text, uint32_t fg, uint32_t bg)
{
	if (row >= g_screen.rows || row >= BP_MAX_ROWS) {
		return;
	}
	bp_copy(g_screen.model[row], text);
	g_screen.model_fg[row] = fg;
	g_screen.model_bg[row] = bg;
}

/* Push the model to the panel, touching only the cells whose character or colour changed. */
static void
bp_flush(void)
{
	unsigned row, column;

	if (!g_screen.bound) {
		return;
	}
	for (row = 0; row < g_screen.rows && row < BP_MAX_ROWS; row++) {
		char *shown = g_screen.shown[row];
		const char *wanted = g_screen.model[row];
		int recolour = !g_screen.painted ||
		    g_screen.shown_fg[row] != g_screen.model_fg[row] ||
		    g_screen.shown_bg[row] != g_screen.model_bg[row];

		for (column = 0; column < g_screen.cols; column++) {
			char want = wanted[column];

			if (!recolour && shown[column] == want) {
				continue;
			}
			bp_cell(row, column, want != 0 ? want : ' ',
			    g_screen.model_fg[row], g_screen.model_bg[row]);
			shown[column] = want;
		}
		shown[g_screen.cols] = 0;
		g_screen.shown_fg[row] = g_screen.model_fg[row];
		g_screen.shown_bg[row] = g_screen.model_bg[row];
	}
	g_screen.painted = 1;
}

/* Compose every row from the current state and push it. Called on each event, so the row text
 * has to be rebuilt cheaply: no allocation, fixed buffers, no formatting library. */
static void
bp_build(void)
{
	char line[BP_MAX_COLS + 1];
	struct bp_out out;
	unsigned index, panel;

	bp_model_row(0, " XNU BOOT PROGRESS  min-1 ", BP_INK, BP_WHITE);

	bp_out_begin(&out, line);
	bp_out_puts(&out, "STG=");
	bp_out_dec(&out, g_state.stages);
	bp_out_puts(&out, " IRQ=");
	bp_out_dec(&out, g_state.irqs);
	bp_out_puts(&out, " FAULT=");
	bp_out_dec(&out, g_state.faults);
	bp_out_puts(&out, " BRK=");
	bp_out_dec(&out, g_state.breakpoints);
	bp_out_puts(&out, g_state.start_seen ? " STARTED" : " EARLY");
	bp_model_row(1, line, BP_AMBER, BP_BLACK);

	/* Before the ring wraps, the used slots sit at the bottom of the index space, so the display
	 * starts at slot zero and leaves the unused slots blank at the end. Once it wraps, the oldest
	 * surviving line is the one the write cursor is about to overwrite. */
	{
		unsigned count = g_state.log_count + 1u;
		unsigned visible = count < BP_LOG_LINES ? count : BP_LOG_LINES;
		unsigned first = count < BP_LOG_LINES ? 0u : count % BP_LOG_LINES;

		for (index = 0; index < BP_LOG_LINES; index++) {
			unsigned slot = (first + index) % BP_LOG_LINES;

			bp_out_begin(&out, line);
			if (index < visible && g_state.log[slot][0] != 0) {
				/* The open line has a number but no text yet; printing the number alone
				 * would look like a line whose contents were lost. */
				bp_out_dec(&out, g_state.log_number[slot]);
				bp_out_puts(&out, " ");
				bp_out_puts(&out, g_state.log[slot]);
			}
			bp_model_row(2u + index, line,
			    slot == g_state.log_row ? BP_WHITE : BP_GREY, BP_BLACK);
		}
	}

	panel = 2u + BP_LOG_LINES + 1u;
	bp_model_row(panel + 0, g_state.last, BP_GREEN, BP_BLACK);
	bp_model_row(panel + 1, g_state.process, BP_BLUE, BP_BLACK);
	bp_model_row(panel + 2, g_state.brk, BP_RED, BP_BLACK);
	bp_model_row(panel + 3, g_state.abort_line, BP_RED, BP_BLACK);
	bp_model_row(panel + 4, g_state.exit_line, BP_BLUE, BP_BLACK);
	bp_model_row(panel + 5, g_state.critical, BP_RED, BP_BLACK);
}

static void
bp_refresh(void)
{
	if (!g_screen.bound) {
		return;
	}
	bp_build();
	bp_flush();
}

/* ------------------------------------------------------------------------------- log line model */

static void
bp_newline(void)
{
	/* Closing an empty line would only burn a slot and leave a gap in the log, so a caller that
	 * ends a message and a console writer that follows it can both ask for a new line without
	 * the two requests stacking up. */
	if (!g_state.line_dirty) {
		return;
	}
	g_state.log_count++;
	g_state.log_row = g_state.log_count % BP_LOG_LINES;
	g_state.log_number[g_state.log_row] = g_state.log_count;
	g_state.log[g_state.log_row][0] = 0;
	g_state.line_dirty = 0;
}

static void
bp_character(char character)
{
	char *slot = g_state.log[g_state.log_row];
	unsigned length = 0;

	while (length < BP_MAX_COLS && slot[length] != 0) {
		length++;
	}
	if (length >= BP_MAX_COLS) {
		bp_newline();
		slot = g_state.log[g_state.log_row];
		length = 0;
	}
	slot[length] = character;
	slot[length + 1u] = 0;
	g_state.line_dirty = 1;
}

/* ------------------------------------------------------------------------------- event handlers */

int
boot_progress_active(void)
{
	/* Only claim the console once there is a validated screen to redirect it to. Before the
	 * bind the console keeps working exactly as it does in a build without this file. */
	return g_state.initialized && g_screen.bound;
}

void
boot_progress_init(void)
{
	unsigned index;

	if (g_state.initialized) {
		return;
	}
	g_state.initialized = 1;
	g_state.log_row = 0;
	g_state.log_count = 0;
	for (index = 0; index < BP_LOG_LINES; index++) {
		g_state.log[index][0] = 0;
		g_state.log_number[index] = 0;
	}
	g_state.last[0] = 0;
	g_state.process[0] = 0;
	g_state.brk[0] = 0;
	g_state.abort_line[0] = 0;
	g_state.exit_line[0] = 0;
	g_state.critical[0] = 0;
	g_state.line_dirty = 0;
}

void
boot_progress_bind(uintptr_t base, unsigned width, unsigned height, unsigned rowbytes, unsigned depth)
{
	uintptr_t framebuffer = base;
	unsigned scale;

	/* The geometry comes from vinfo, which the console filled from boot_args. Reject anything
	 * that cannot be a 32bpp scan-out buffer before the first store, so a board that reports
	 * nonsense leaves the screen alone instead of faulting on it. */
	if (depth != 32 || base == 0 || (base & 3u) != 0) {
		return;
	}
	if (width < 320 || width > 8192 || height < 240 || height > 8192) {
		return;
	}
	if (rowbytes < width * 4u || rowbytes > width * 4u + 16384u) {
		return;
	}
	if (!bp_translated(framebuffer)) {
		/* arm_vm_init() replaced the identity map, so the physical address is reachable only
		 * through the aperture. Zero until the aperture is installed. */
		uintptr_t aperture = (uintptr_t) physmap_base;

		if (aperture == 0 || !bp_translated(aperture + framebuffer)) {
			return;
		}
		framebuffer = aperture + framebuffer;
	}
	/* Pick the largest legible cell that still leaves room for the whole layout: title, counter
	 * row, the log and the panel. A panel too short for that gets no observer at all rather than
	 * a truncated one, and the console keeps working because the bind simply does not happen. */
	for (scale = 8; scale > 0; scale--) {
		if (width / (6u * scale) >= 56 &&
		    height / (14u * scale) >= 3u + BP_LOG_LINES + BP_PANEL_LINES) {
			break;
		}
	}
	if (scale == 0) {
		return;
	}
	g_screen.fb = (volatile uint32_t *) framebuffer;
	g_screen.width = width;
	g_screen.height = height;
	g_screen.stride = rowbytes;
	g_screen.scale = scale;
	g_screen.cols = width / (6u * scale);
	g_screen.rows = height / (14u * scale);
	if (g_screen.cols > BP_MAX_COLS) {
		g_screen.cols = BP_MAX_COLS;
	}
	if (g_screen.rows > BP_MAX_ROWS) {
		g_screen.rows = BP_MAX_ROWS;
	}
	if (g_screen.rows < 3u + BP_LOG_LINES + BP_PANEL_LINES) {
		return;
	}
	g_screen.painted = 0;
	g_screen.bound = 1;
	bp_refresh();
}

void
boot_progress_start(void)
{
	g_state.start_seen = 1;
	bp_copy(g_state.last, "LAST: clock service created; scheduler running");
	bp_refresh();
}

void
boot_progress_stage(const char *text)
{
	char line[BP_MAX_COLS + 1];
	struct bp_out out;

	g_state.stages++;
	if (text == NULL) {
		return;
	}
	/* Every stage lands in the panel and in the log, so the screen shows the last milestone
	 * reached even when the log has wrapped past it. */
	bp_out_begin(&out, line);
	bp_out_puts(&out, "LAST: ");
	bp_out_puts(&out, text);
	bp_copy(g_state.last, line);

	bp_out_begin(&out, line);
	bp_out_puts(&out, text);
	{
		unsigned length = out.used;

		/* Close whatever console text was still open, write the milestone on a line of its
		 * own, then close that too: the console output that follows must not run into it. */
		bp_newline();
		for (unsigned index = 0; index < length && index < BP_MAX_COLS; index++) {
			bp_character(line[index]);
		}
		bp_newline();
	}
	bp_refresh();
}

void
boot_progress_putc(char character)
{
	if (!g_state.initialized) {
		return;
	}
	if (character == '\r') {
		return;
	}
	if (character == '\n') {
		bp_newline();
		bp_refresh();
		return;
	}
	if (character == '\t') {
		character = ' ';
	}
	if (character < 32 || character > 126) {
		return;
	}
	bp_character(character);
	bp_refresh();
}

void
boot_progress_irq(uint64_t pc, uint64_t cpsr, uint64_t sp)
{
	(void) pc;
	(void) cpsr;
	(void) sp;
	g_state.irqs++;
	/* A heartbeat must not cost a repaint per interrupt: refresh on every 4096th only, which is
	 * still fine-grained enough to show the machine was alive up to the last stage. */
	if ((g_state.irqs & 0xfffu) == 0) {
		bp_refresh();
	}
}

void
boot_progress_poll(void)
{
	bp_refresh();
}

/* Read the user pc out of the exception frame. The frame is arm_saved_state_t: an eight byte
 * {flavor, count} header followed by arm_saved_state64_t, whose pc sits after x[29], fp, lr and
 * sp. Both header fields are checked, so a frame of another flavour is reported as unknown
 * instead of being misread. */
static uint64_t
bp_frame_pc(void *state)
{
	const volatile uint32_t *header;
	unsigned count;

	if (state == NULL || !bp_readable(state)) {
		return 0;
	}
	header = (const volatile uint32_t *) state;
	if (header[0] != 6u) {                                  /* ARM_THREAD_STATE64 */
		return 0;
	}
	count = header[1];
	if (count != 72u && count != 74u) {                      /* with and without the PAC hash */
		return 0;
	}
	return *(const volatile uint64_t *) ((const volatile char *) state + 8u + 256u);
}

void
boot_progress_user_breakpoint(void *state, unsigned esr)
{
	char line[BP_MAX_COLS + 1];
	struct bp_out out;
	uint64_t pc = bp_frame_pc(state);

	g_state.breakpoints++;
	bp_out_begin(&out, line);
	bp_out_puts(&out, "BRK : n=");
	bp_out_dec(&out, g_state.breakpoints);
	bp_out_puts(&out, " pc=");
	bp_out_hex(&out, pc, 16);
	bp_out_puts(&out, " esr=");
	bp_out_hex(&out, esr, 8);
	bp_copy(g_state.brk, line);
	bp_refresh();
}

void
boot_progress_user_abort(void *state, unsigned esr, uint64_t fault_addr)
{
	char line[BP_MAX_COLS + 1];
	struct bp_out out;

	g_state.faults++;
	bp_out_begin(&out, line);
	bp_out_puts(&out, "ABRT: pc=");
	bp_out_hex(&out, bp_frame_pc(state), 16);
	bp_out_puts(&out, " far=");
	bp_out_hex(&out, fault_addr, 10);
	bp_out_puts(&out, " esr=");
	bp_out_hex(&out, esr, 8);
	bp_copy(g_state.abort_line, line);
	bp_refresh();
}

void
boot_progress_process_stage(int pid, const char *name, const char *stage)
{
	char line[BP_MAX_COLS + 1];
	struct bp_out out;

	bp_out_begin(&out, line);
	bp_out_puts(&out, "PROC: ");
	bp_out_dec(&out, (uint64_t) (unsigned) pid);
	bp_out_puts(&out, " ");
	bp_copy_probed(g_state.process, name, 20);
	bp_out_puts(&out, g_state.process);
	bp_out_puts(&out, " ");
	if (stage != NULL && bp_readable(stage)) {
		bp_out_puts(&out, stage);
	}
	bp_copy(g_state.process, line);
	bp_refresh();
}

void
boot_progress_critical_exit(int pid, char *prefix, unsigned long length)
{
	char line[BP_MAX_COLS + 1];
	struct bp_out out;
	unsigned limit = (unsigned) length;
	unsigned index;

	if (limit > BP_MAX_COLS) {
		limit = BP_MAX_COLS;
	}
	bp_out_begin(&out, line);
	bp_out_puts(&out, "CRIT: ");
	bp_out_dec(&out, (uint64_t) (unsigned) pid);
	bp_out_puts(&out, " ");
	if (prefix != NULL && bp_readable(prefix)) {
		for (index = 0; index < limit && prefix[index] != 0; index++) {
			char character = prefix[index];

			if (character < 32 || character > 126) {
				continue;
			}
			if (out.used < BP_MAX_COLS) {
				out.text[out.used++] = character;
				out.text[out.used] = 0;
			}
		}
	}
	bp_copy(g_state.critical, line);
	bp_refresh();
}

void
boot_progress_exit(int pid, const char *name, int rv, unsigned namespace_id, uint64_t code)
{
	char line[BP_MAX_COLS + 1];
	struct bp_out out;

	bp_out_begin(&out, line);
	bp_out_puts(&out, "EXIT: ");
	bp_out_dec(&out, (uint64_t) (unsigned) pid);
	bp_out_puts(&out, " ");
	bp_copy_probed(g_state.exit_line, name, 20);
	bp_out_puts(&out, g_state.exit_line);
	bp_out_puts(&out, " rv=");
	bp_out_dec(&out, (uint64_t) (unsigned) rv);
	bp_out_puts(&out, " ns=");
	bp_out_dec(&out, namespace_id);
	bp_out_puts(&out, " code=");
	bp_out_dec(&out, code);
	bp_copy(g_state.exit_line, line);
	bp_refresh();
}
