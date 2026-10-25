# Preprocessing implementation status

The earlier guard-only change has been superseded. Python now implements the
validated masonry Quad/fixed-Restraint subset of C#
`ModelManager.PrepareModel`. See:

- `RAW_HRX_PREPROCESSING.md`
- `PREPROCESSING_FINAL_REPORT.md`
- `histra/histra_documentation/PREPROCESSING.md`

Unsupported topologies still fail explicitly rather than producing a partial
computational model.
