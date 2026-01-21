# Common Notes

## Cross-platform strategy
- Keep DB/Importer/Exporter in pure Python
- Keep UI layer thin
- For GTK builds: bundle GTK runtime + schemas + loaders per OS

## Alternative
If packaging GTK becomes too heavy: keep backend and switch UI to Qt (PySide6) for smoother Win/mac installers.
