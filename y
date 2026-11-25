Expand-Archive -Force $HOME\Downloads\changed_files_127.zip .
git add README.md studio tests
git commit -m "Translate German SCORM content and add a Data tab with topics and sources"
git push
uv run -m studio inventory
uv run -m studio pipeline --mode all --vision
uv run -m studio topics
