Expand-Archive -Force $HOME\Downloads\changed_files_119.zip .
git add README.md studio tests
git commit -m "SCORM reader"
git push

Copy-Item -Recurse $HOME\Downloads\Scrum data\input\Scrum

uv run -m studio scorm

uv run -m studio pipeline --mode easy

uv run -m studio pipeline --mode all
