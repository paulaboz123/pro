Expand-Archive -Force $HOME\Downloads\changed_files_121.zip .
git add studio tests
git commit -m "Read more caption formats and report unreadable SCORM packages"
git push
uv run -m studio inventory
uv run -m studio scorm_report
