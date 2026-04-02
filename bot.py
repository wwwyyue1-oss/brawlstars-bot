
## **Як це все завантажити на GitHub:**

```bash
# 1. Створіть нову папку проекту
mkdir brawl-bot
cd brawl-bot

# 2. Скопіюйте всі файли (bot.py, requirements.txt, .env.example, .gitignore, Dockerfile)

# 3. Ініціалізуйте Git
git init

# 4. Додайте файли (окрім .env, який в .gitignore)
git add bot.py requirements.txt .env.example .gitignore Dockerfile docker-compose.yml README.md

# 5. Створіть коміт
git commit -m "Initial commit: Brawl Stars Telegram Bot with environment variables"

# 6. Підключіть віддалений репозиторій
git remote add origin https://github.com/ваш_логін/brawl-bot.git

# 7. Завантажте на GitHub
git push -u origin main
