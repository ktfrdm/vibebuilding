# Инструкция по подключению GitHub и настройке релизов

## Шаг 1: Создание репозитория на GitHub

1. Перейдите на [GitHub.com](https://github.com) и войдите в свой аккаунт
2. Нажмите кнопку **"+"** в правом верхнем углу и выберите **"New repository"**
3. Заполните форму:
   - **Repository name**: `вайб` (или другое название)
   - **Description**: Краткое описание вашего проекта
   - **Visibility**: Выберите Public (публичный) или Private (приватный)
   - **НЕ** добавляйте README, .gitignore или лицензию (они уже есть в проекте)
4. Нажмите **"Create repository"**

## Шаг 2: Инициализация Git в проекте

Откройте терминал в корневой папке проекта и выполните следующие команды:

### 2.1. Инициализация Git (если еще не инициализирован)

```bash
git init
```

### 2.2. Добавление всех файлов в staging area

```bash
git add .
```

### 2.3. Создание первого коммита

```bash
git commit -m "Initial commit: структура проекта Telegram-бота"
```

## Шаг 3: Подключение к удаленному репозиторию

### 3.1. Добавление удаленного репозитория

Замените `YOUR_USERNAME` и `YOUR_REPO_NAME` на ваши данные:

```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

**Пример:**
```bash
git remote add origin https://github.com/ekaterinabazhenova/вайб.git
```

### 3.2. Проверка подключения

```bash
git remote -v
```

Вы должны увидеть:
```
origin  https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git (fetch)
origin  https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git (push)
```

### 3.3. Переименование основной ветки в main (если нужно)

```bash
git branch -M main
```

### 3.4. Отправка кода на GitHub

```bash
git push -u origin main
```

Если Git запросит авторизацию:
- **Для HTTPS**: Используйте Personal Access Token вместо пароля
- **Для SSH**: Настройте SSH ключи (см. раздел "Альтернатива: Использование SSH")

## Шаг 4: Настройка .gitignore

Убедитесь, что файл `.gitignore` содержит все необходимые исключения. Он уже создан в проекте и включает:
- `.env` (важные данные не должны попадать в репозиторий!)
- `__pycache__/`
- `venv/`
- и другие

**⚠️ ВАЖНО:** Никогда не коммитьте файл `.env` с реальными токенами!

## Шаг 5: Работа с ветками (опционально)

### Создание ветки для разработки

```bash
git checkout -b develop
```

### Переключение между ветками

```bash
git checkout main      # Переключиться на main
git checkout develop   # Переключиться на develop
```

### Отправка ветки на GitHub

```bash
git push -u origin develop
```

## Шаг 6: Настройка релизов (Releases) в GitHub

### 6.1. Создание тега для версии

#### Способ 1: Через командную строку

```bash
# Создать аннотированный тег
git tag -a v1.0.0 -m "Релиз версии 1.0.0"

# Отправить тег на GitHub
git push origin v1.0.0
```

#### Способ 2: Через GitHub веб-интерфейс

1. Перейдите на страницу вашего репозитория на GitHub
2. Нажмите на **"Releases"** в правой панели (или перейдите по ссылке `https://github.com/YOUR_USERNAME/YOUR_REPO_NAME/releases`)
3. Нажмите **"Create a new release"**
4. Заполните форму:
   - **Choose a tag**: Создайте новый тег (например, `v1.0.0`)
   - **Release title**: Название релиза (например, "Версия 1.0.0 - Первый релиз")
   - **Description**: Описание изменений (можно использовать Markdown)
   - **Set as the latest release**: Отметьте, если это последний релиз
5. Нажмите **"Publish release"**

### 6.2. Формат версий (Semantic Versioning)

Рекомендуется использовать формат `MAJOR.MINOR.PATCH`:

- **MAJOR** (1.0.0) - Несовместимые изменения API
- **MINOR** (0.1.0) - Новая функциональность, обратно совместимая
- **PATCH** (0.0.1) - Исправления ошибок, обратно совместимые

**Примеры:**
- `v1.0.0` - Первый стабильный релиз
- `v1.1.0` - Добавлена новая функция
- `v1.1.1` - Исправлена ошибка
- `v2.0.0` - Крупное обновление с несовместимыми изменениями

### 6.3. Шаблон описания релиза

```markdown
## 🎉 Что нового

### ✨ Новые функции
- Функция 1
- Функция 2

### 🐛 Исправления
- Исправлена ошибка 1
- Исправлена ошибка 2

### 🔧 Улучшения
- Улучшение 1
- Улучшение 2

## 📦 Установка

```bash
pip install -r requirements.txt
```

## 📝 Изменения

Полный список изменений доступен в [CHANGELOG.md](../CHANGELOG.md)
```

## Шаг 7: Автоматизация релизов (опционально)

### 7.1. Создание GitHub Actions для автоматических релизов

Создайте файл `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run tests
        run: python -m pytest tests/
      
      - name: Create Release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          body: |
            Автоматический релиз версии ${{ github.ref }}
          draft: false
          prerelease: false
```

### 7.2. Создание CHANGELOG.md

Создайте файл `CHANGELOG.md` в корне проекта для отслеживания изменений:

```markdown
# Changelog

Все важные изменения в проекте будут документироваться в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
и проект придерживается [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [1.0.0] - 2026-02-04

### Added
- Первоначальная структура проекта
- Базовая функциональность бота
- Документация проекта

[Unreleased]: https://github.com/YOUR_USERNAME/YOUR_REPO_NAME/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/YOUR_USERNAME/YOUR_REPO_NAME/releases/tag/v1.0.0
```

## Шаг 8: Полезные команды Git

### Просмотр статуса

```bash
git status
```

### Просмотр истории коммитов

```bash
git log --oneline --graph --all
```

### Просмотр всех тегов

```bash
git tag -l
```

### Удаление тега (локально и удаленно)

```bash
git tag -d v1.0.0                    # Удалить локально
git push origin --delete v1.0.0     # Удалить на GitHub
```

### Обновление локального репозитория

```bash
git pull origin main
```

### Отправка изменений

```bash
git add .
git commit -m "Описание изменений"
git push origin main
```

## Альтернатива: Использование SSH

Если вы предпочитаете использовать SSH вместо HTTPS:

### 1. Генерация SSH ключа

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

### 2. Добавление ключа в ssh-agent

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### 3. Добавление ключа на GitHub

1. Скопируйте публичный ключ:
```bash
cat ~/.ssh/id_ed25519.pub
```

2. На GitHub: Settings → SSH and GPG keys → New SSH key
3. Вставьте ключ и сохраните

### 4. Изменение URL удаленного репозитория

```bash
git remote set-url origin git@github.com:YOUR_USERNAME/YOUR_REPO_NAME.git
```

## Troubleshooting

### Ошибка: "remote origin already exists"

```bash
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
```

### Ошибка авторизации при push

1. Проверьте, что используете Personal Access Token (не пароль)
2. Или настройте SSH ключи

### Откат последнего коммита (еще не запушен)

```bash
git reset --soft HEAD~1
```

### Откат последнего коммита (уже запушен)

```bash
git revert HEAD
git push origin main
```

## Полезные ссылки

- [GitHub Docs](https://docs.github.com/)
- [Git Documentation](https://git-scm.com/doc)
- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
