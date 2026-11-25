Expand-Archive -Force $HOME\Downloads\changed_files_118.zip .
git add README.md studio tests
git commit -m "Look: Default or Domain"
git push


uv run --no-project python $HOME\Downloads\scorm_inspect.py "$HOME\Downloads\Scrum"
uv run --no-project python $HOME\Downloads\scorm_inspect.py "$HOME\Downloads\Scrum" --deep
