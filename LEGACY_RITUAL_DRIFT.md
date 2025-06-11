# Legacy Ritual Drift

Some helper modules were written before strict privilege banner requirements
took effect. They load only when imported and do not display the standard
banner on startup. Their behavior remains stable, but we keep them isolated and
document this gap for future refactoring.
