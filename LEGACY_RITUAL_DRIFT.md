# Legacy Ritual Drift

Some helper modules were written before privilege banners became mandatory. They
load only when imported and do not display the standard banner on startup. Their
behavior remains stable, but we keep them isolated and document this gap for
future refactoring.
