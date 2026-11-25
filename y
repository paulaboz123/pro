Expand-Archive -Force $HOME\Downloads\changed_files_123.zip .
git add studio tests
git commit -m "Keep quiz questions with known answers and read sentences under any field"
git push
uv run -m studio inventory
uv run -m studio scorm_report
