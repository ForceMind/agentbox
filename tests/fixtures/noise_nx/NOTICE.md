# Independent Noise NX test vector

This fixture is public deterministic test material, including published test
private keys. It is not production key material or an AgentBox host identity.

- Source repository: [rweather/noise-c](https://github.com/rweather/noise-c).
- Pinned commit: `5d0a74760320e5486ced302e36ccad91606aac43`.
- Source file: [noise-c-basic.txt](https://github.com/rweather/noise-c/blob/5d0a74760320e5486ced302e36ccad91606aac43/tests/vector/noise-c-basic.txt).
- Source file SHA-256: `e826749cf90efda26be85410381f4b1f75552c61c7c0dcad7f9ffb4d639e4e45`.
- Selected vector: `Noise_NX_25519_AESGCM_SHA256`; all fields retained.
- Selected JSON SHA-256: `24655e652e3474c8bd0531a05a5ecb30bb0e750d93c6d9a40157ef33c0fb9722`.
- Transformation: extract the one named vector and serialize JSON with two-space indentation and a final LF. Hex field contents are unchanged.
- This is a Noise Wiki-listed independent Noise-C vector, not a vector generated
  by our implementation or a claim about a newer host/browser deployment.
- Protocol reference: [Noise revision 34](https://noiseprotocol.org/noise.html).
- License: MIT, exact upstream [COPYING](https://github.com/rweather/noise-c/blob/5d0a74760320e5486ced302e36ccad91606aac43/COPYING) follows.

```text
Copyright (C) 2016 Southern Storm Software, Pty Ltd.

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
```
