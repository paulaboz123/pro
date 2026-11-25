Expand-Archive -Force $HOME\Downloads\changed_files_125.zip .
git add studio tests
git commit -m "Keep slide bullet points from SCORM data and read wbt.json.js copies once"
git push
uv run -m studio inventory
uv run -m studio scorm_report
