# legacy/

Quarantine area for code imported from outside this repository.

`legacy/mvp/` will hold the original local TradeMind MVP, imported with `scripts/import_mvp.ps1`.
Code here is **reference material only**:

- it is never imported by `backend/trademind`, packaged, deployed, or collected by CI tests;
- each piece is ported into its canonical module (see `docs/MVP_INTEGRATION.md`) and then deleted;
- the folder is removed entirely once porting is complete.
