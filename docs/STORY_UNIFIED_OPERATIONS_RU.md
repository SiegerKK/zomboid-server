# Единое управление Story Director — Build 42.21.0

Это API для существующего **story_test**. Только root через sudo pz story.
Нет произвольного Lua, RCON eval, клиентских команд, сброса мира или
автоматического восстановления бэкапов. Приватные файлы с инвентарями
остаются вне публичного репозитория.

## 1. Параметризованный скан v3

    sudo pz story scan-area story_test --player admin \
      --center 10622,9221 --radius 20 --z-min 0 --z-max 1 \
      --include squares,objects,containers,items,ground,actors,corpses,vehicles,windows,blood --yes
    sudo pz story scan-status story_test
    sudo pz story scan-report story_test --output /var/tmp/smokeys-v3.json

Все настройки указываются в команде, коммит не нужен.

- Центр не обязателен: без него используем точного онлайн-игрока. Явно
  заданный центр не дальше 100 клеток от этого игрока.
- Radius от 1 до 50: квадрат (2R+1)×(2R+1). Z-min/max включительно,
  1..5 этажей от -2 до 16. Никогда не загружаем чанки принудительно.
- Категории: squares, objects, containers, items, ground, actors,
  corpses, vehicles, windows, blood. Для blood нужны squares; для items —
  containers. Actors/corpses включают только Story-помеченные сущности.
- Vehicles: загруженные машины в области, ID, точный script, детали,
  состояние и инвентари GloveBox/Trunk по vehicle_id/part_id. Механика
  спавна машин не включена и требует отдельной игровой приёмки.
- Лёгкий пример:
  
      sudo pz story scan-area story_test --player admin \
        --radius 6 --z-min 0 --z-max 0 \
        --include squares,objects,windows,blood --yes

Команды scan-player --side 25/51/101 сохраняются. Исторические JSON
не становятся новыми сканами автомобилей задним числом.

## 2. Разовая постановка без JSON-файла в Git

    # Просмотр без изменений: нет --yes.
    sudo pz story apply-once story_test --key water_supply_001 \
      --type loot --x 10618 --y 9216 --z 0 \
      --placement ground --item Base.Bandage --count 2

    # Применение с тем же стабильным ключом:
    sudo pz story apply-once story_test --key water_supply_001 \
      --type loot --x 10618 --y 9216 --z 0 \
      --placement ground --item Base.Bandage --count 2 --yes
    sudo pz story live-status story_test

Поддерживаются только note, loot, infected и строго ограниченный corpse.
Для note: --title и --text (одна страница). Для контейнера:
--placement container --target-index N --target-sprite EXACT_SPRITE.
Для infected требуется --allow-infected; для corpse: --allow-corpses,
--floor-sprite и необязательный --blood 0..3.
Стабильный --key образует scene id ops_KEY и action id action_001.
Повтор ключа в одной сессии запрещён; при новой сессии отметки на клетке
предотвращают дублирование. Никогда не меняйте смысл уже применённого ключа.
Постановки хранятся в приватных файлах сессии, не в Git.
Нужна открытая live-сессия на story_test.

## 3. Игрок: онлайн-диагностика и ограниченные операции

    sudo pz story player-inspect story_test GAME_LOGIN --yes
    sudo pz story player-status story_test

    sudo pz story player-grant story_test GAME_LOGIN \
      --item Base.Bandage --count 2 --yes
    sudo pz story player-status story_test

    sudo pz story player-remove-tagged story_test GAME_LOGIN \
      --token SiegerStory:admin_player_ops:grant_item:REQUEST_ID:1 --yes

    sudo pz story player-heal story_test GAME_LOGIN \
      --experimental-health --yes

Инвентарь пока верхнего уровня (не рюкзаки), максимум 256 предметов.
Метрики здоровья, стресса, усталости, голода и жажды возвращаются через
доступные в данной сборке getter'ы, иначе значение unavailable.
Выдача ограничена 8 обычными предметами, 1..5 за запрос. Удалять можно
только точно указанный Story-токен в главном инвентаре. Удаление чужих
или экипированных предметов запрещено.

Лечение вызывает RestoreToFullHealth на серверных частях тела, но его
синхронизация с B42 multiplayer **НЕ подтверждена в игре**; потому команда
только экспериментальная и требует отдельного подтверждения владельца
персонажа и проверки через клиент/перезаход.

Сервер запоминает идентификатор попытки до мутации; при неоднозначном
результате не повторяет выдачу/лечение автоматически. После ручного разбора
ошибки следующий запрос допускает флаг --acknowledge-failed.

## 4. Измерение нагрузки, а не предположения

    sudo pz story profile story_test --samples 12 --interval 5 \
      --output /var/tmp/story-idle-profile.json

    sudo pz story profile story_test --samples 20 --interval 5 \
      --output /var/tmp/story-active-profile.json

Профиль берётся из docker stats --no-stream, с min/median/max CPU и
median/max RAM/лимитом. Это метрики всего игрового контейнера: они
**не отделяют** Java/ваниль/Forge/TLOU/ZombieBuddy от Story Lua.

Ранее задокументированный реальный скан 101×101×5 (PR #9) длился около
280,6 с, использовал около 9,43 GiB из лимита 12 GiB. Это показатель
общего потребления в течение скана, не постоянная память нашего мода.

Периодическая работа модулей:
- AreaScan: маленький OnTick check, чтение файла запроса раз в 120 тиков
  без активного задания. Активный проход — до 20 клеток/200 шагов за тик
  и потоковая запись, без хранения 51 тысячи клеток как Lua массива.
- Director: live-проверка раз в 60 тиков, проверка координат статических
  сцен раз в 300 тиков. Завершённые действия в новой версии удаляются из
  рабочей очереди, а флаги в игровом мире сохраняются.
- PlayerControl: чтение корневого файла раз в 120 тиков; игроки и их
  инвентари не перебираются, пока нет запроса.

Без сравнимых замеров idle/с игроками/во время скана нельзя говорить,
сколько именно CPU/RAM отнимает Story Director. Для доказательства эффекта
понадобятся одинаковые нагрузки, проверка GC и tick/lag на JVM.
Docker CPU% может превышать 100 на многоядерной машине.

## 5. Порядок безопасной приёмки

1. CI и pinned Build 42.21 Java/Kahlua тесты, затем short restart только
   игрового контейнера при RCON players=0 с холодным контрольным бэкапом.
2. Проверить mounts: Director, AreaScan, PlayerControl и Story bundle.
   Никогда не менять road_home или Workshop без согласования.
3. Проверить scan-area сначала радиус 2 / один этаж, потом радиус 20.
   Не принимать PARTIAL или UNLOADED за полный архитектурный снимок.
4. Проверить player-inspect на тестовом персонаже, grant и удаление
   только нового Story-токена, затем опционально экспериментальный heal
   под наблюдением игрока.
5. Проверить apply-once dry-run, затем однократный малый предмет с меткой,
   client sync/повтор/перезаход.
6. Снять CPU/RAM idle и при нагруженном скане; результаты опубликовать
   отдельно с пометкой про нагрузку всего Docker.
7. Оставить story_test со всеми изменениями, никаких автоматических откатов.

Разрушительные операции над окнами, удаление не-квестовых вещей,
спавн машин и правка автомобильных инвентарей в этот API **не включены**:
сначала нужны точные селекторы и проверенный dedicated multiplayer runtime.
