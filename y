Wpisz po kolei:

git checkout main
git pull
Expand-Archive -Force $HOME\Downloads\changed_files_109.zip .

2. Dodaj tylko kod:

git add README.md studio tests
git status

W „Changes to be committed” mają być tylko README.md i pliki z studio/ i tests/. Nie może tam być kb.tgz.

3. Wyślij:

git commit -m "Clara's changes: two tabs, clearer outputs, company look"
git push
