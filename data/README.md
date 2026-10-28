# Data folder (private - stays on your computer)

| File | Contents |
|---|---|
| `linguaai.db` | SQLite database: sessions, messages (text), feedback, vocabulary, practice attempts, learning profile. Created on first launch. |
| `settings.json` | Technical settings you changed in the app (models, limits). Created when you press Save in Settings. |
| `exercises/pronunciation.json` | Built-in pronunciation practice sentences (you can add your own sets in the same format). |

No audio recordings are stored. See `docs/PRIVACY.md` for how to export or delete your data.
These files are listed in `.gitignore` so they are never committed to Git by accident.
