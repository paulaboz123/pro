Expand-Archive -Force $HOME\Downloads\changed_files_124.zip .
git add studio tests
git commit -m "Read SCORM course text kept under a settings field"
git push
uv run -m studio inventory
uv run -m studio scorm_report
