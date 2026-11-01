#!/bin/bash
# Decrypt the images artifact of the packaging run.
# usage: ci/decrypt-images.sh <encrypted-dir> <boot-image-owner.key>
set -euo pipefail
dir=${1:?encrypted artifact directory}
key=${2:?path to boot-image-owner.key}

openssl pkeyutl -decrypt -inkey "$key" -in "$dir/boot.key.enc" -out "$dir/boot.key" \
  -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -salt \
  -in "$dir/images.tar.gz.enc" -out "$dir/images.tar.gz" -pass file:"$dir/boot.key"
tar -xzf "$dir/images.tar.gz" -C "$dir"
rm -f "$dir/boot.key" "$dir/images.tar.gz"
ls -l "$dir"
