Expand-Archive -Force $HOME\Downloads\changed_files_122.zip .
git add studio tests
git commit -m "Skip font files in SCORM packages, read texts under media and language fields"
git push
uv run -m studio inventory
uv run -m studio scorm_report
