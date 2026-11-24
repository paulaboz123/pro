uv run --no-project python $HOME\Downloads\scorm_inspect.py "C:\ścieżka\do\folderu z plikami SCORM"

git checkout main
git pull
Expand-Archive -Force $HOME\Downloads\changed_files_114.zip .
git add README.md studio tests
git status
git commit -m "Sources list and quality notes"
git push


