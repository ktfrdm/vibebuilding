# Миграции Supabase для бота Vibe

После создания проекта в [Supabase](https://supabase.com):

1. Откройте **SQL Editor** в дашборде проекта.
2. Скопируйте содержимое файла `migrations/001_initial.sql` и выполните запрос.
3. Убедитесь, что таблицы созданы: **Table Editor** → `meetings`, `participants`, `participant_selection`, `user_states`.
4. В настройках проекта (**Project Settings** → **API**) скопируйте **Project URL** и **service_role** key.
5. Добавьте в `.env` (и в переменные Railway):
   - `SUPABASE_URL=<Project URL>`
   - `SUPABASE_SERVICE_KEY=<service_role key>`

После этого бот будет использовать БД при заданных переменных окружения.
