/*
 * Entry point the kernel calls once the I/O Kit registry is up.
 *
 * HackiOS starts its Mini drivers from GenericARMPE, which this tree does not carry. The provider
 * those drivers attach to is the platform expert either way, and IOService::getPlatform() is the
 * published way to reach it, so the call site stays a single C function that bsd_init.c can call.
 *
 * redwood_tl is HackiOS's trace helper. It is not part of this kernel: the stub below keeps the
 * driver's call sites compiling and turns the trace into a no-op rather than a log flood.
 */
#include <IOKit/IOService.h>

#include "MiniDrivers.h"

extern "C" void redwood_tl(const char * format, ...) __printflike(1, 2);

extern "C" void
redwood_tl(const char * format, ...)
{
	(void) format;
}

extern "C" void
mini_display_start(void)
{
	IOService * provider = IOService::getPlatform();

	if (provider == NULL) {
		return;
	}
	MiniIOMobileFramebufferStart(provider);
}
