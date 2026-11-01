# ci

`boot-image-recipient.pem` is the RSA public key the packaging workflow encrypts images to.
`boot-image-owner.key`, the matching private key, is not in this repository: keep it offline.
Losing it means the artifacts cannot be decrypted again; a new run is needed.

Decrypt an artifact directory:

```sh
ci/decrypt-images.sh path/to/encrypted boot-image-owner.key
```
