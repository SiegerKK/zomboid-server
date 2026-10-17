# Story Director: фактическая приёмка PR #8

Дата: 2026-10-17 UTC. Этап: runtime `f81f39e` установлен с разрешения владельца;
live-begin и первый apply-live выполнены; обнаружена ошибка навигации страниц, подготовлено исправление для следующего согласованного restart. Все игровые испытания — только story_test.
Ни восстановления checkpoints, ни переключения миров не выполнялись.

| Проверка / команда | Среда | Статус | Доказательство / ограничение |
| --- | --- | --- | --- |
| PR #8, head 4d2f2f2 | GitHub | PASS | Draft/open, исходный CI run 79 SUCCESS |
| Реальная версия игры | VPS story_test | PASS | game log 42.21.0, pinned image 45c602cb… |
| Изоляция Compose/config/scripts | diff vs VPS 9fcf9b5 | PASS | Нет изменений в этих файлах; 12 GiB и прежние mounts сохранены в проекте |
| Python Story/scan/Compose/preset tests, tlou_audit | offline | PASS | 10 Story, 4 live, 6 scan; дополнительные проверки прошли; не доказывают live-мутации |
| bash tests/smoke.sh | VPS /run/story-live-fixed | PASS | Изолированные mock Docker/store, exit 0; реальный world store не использовался |
| Live UTF-8 в original unhex | exact pinned Kahlua | FAIL | Независимый Java Unicode fixture: UTF-8 wire text corrupted |
| Live UTF-8 после исправления | exact pinned Kahlua | PASS | Native live harness с Java fixtures; не игровой клиент |
| pz help/list/status/config story_test/story status | VPS story_test (9fcf9b5) | PASS | Активен story_test, PAUSE_EMPTY=true, bundle без сцен с 25 probes |
| .env permissions | VPS | PASS | root:root 600, содержимое не выводилось |
| Повреждённые ACK: duplicate/count/trailing | offline Python | PASS | Отклонены, pre-commit не разрешён |
| Обновлённые Lua runtime/scan regressions | exact pinned Kahlua | PASS | Оба native harness прошли; реальный Compose config exit 0 |
| Установка PR #8 и live-begin | VPS story_test | PASS | players=0; exit 0; baseline world-20261017T100308Z-85664.tar.gz; сессия open, 0 сцен |
| Runtime / секреты / лимит | VPS story_test | PASS | Смонтированный Lua совпадает с f81f39e; .env hash прежний, 600; cap 12 GiB, только 2 UDP порта |
| Повторный live-begin / commit без сцен | VPS story_test | PASS | Отклонены до остановки; мир продолжил загрузку, сессия без изменений |
| Неверный JSON / coordinate / index / sprite / class / lua field | Installed CLI + isolated source root на VPS | PASS | Отдельные причины отказа, exit 2; никакие запросы в игровой мир не отправлены |
| Запрет внешнего scene path | Installed CLI | PASS | /run/story-live-negative/*.json отвергнуты до разбора; schema cases затем проверены в isolated source root |
| apply-live/live-status без рестарта | VPS story_test | PASS | Оба action ID applied, same container/StartedAt, 0 restarts и LIVE_ERROR |
| Записка / читаемая кириллица | Игровой клиент | PASS | Владелец подтвердил наличие и читаемый русский текст |
| Три страницы в клиентском UI | Игровой клиент | FAIL | UI показывает одну; причина getPageToWrite найдена, fix ещё не развёрнут |
| Два бинта / дезинфектор | Серверный post-scan | PASS | В шкафу точно Base.Bandage=2, Base.Disinfectant=1; клиентское количество требует подтверждения |
| Повторная отправка clinic_live_001 | VPS CLI | PASS | Exit 2: Scene already applied in this session; второй request не создан |
| Выход-вход / сохранность / повторный запуск | VPS + клиент | BLOCKED | Требуется участие владельца после проверки исправленной записки |
| live-commit, оба SHA, sidecar | VPS story_test | BLOCKED | После подтверждения клиентом и выхода игроков |
| Два клиента / MP sync / машина | игровые клиенты | BLOCKED | Требуется участие двух игроков |
| load/create/start другого слота | VPS | BLOCKED | Запрещено текущим тестовым регламентом; только offline regression |
| Восстановление POST/checkpoints | VPS | BLOCKED | Владелец явно запретил восстановление без отдельной команды |
| Искусственное аварийное завершение | VPS | BLOCKED | Риск данных, не выполнялось |
| Live barricade/infected/decor | VPS | BLOCKED | Live adapter не реализован; нельзя выдавать обычных зомби за TLOU |

Команды подготовки на VPS (изолированные тесты):

```bash
bash /run/story-live-review/review/tests/smoke.sh
bash /run/story-live-fixed/tests/smoke.sh
docker exec -w /pzomboid-server pz-source-audit \
  /pzomboid-server/jre64/bin/java \
  -cp /tmp:/pzomboid-server/java/projectzomboid.jar \
  StoryKahluaCheck /tmp/story_live8_fixed.lua /tmp/SiegerStoryDirector8_fixed.lua
```

Runtime установлен, baseline SHA-256 повторно сверён с session.json.
Сессия root/0600, pending_job=null, applied_scenes=0. Игровые сцены не
отправлялись. Все 7223 файла road_home совпали с прежним SHA-256 manifest. Полные инвентари, приватные scan JSON, секреты и saves
в репозиторий не помещаются. PR остаётся Draft до фактической приёмки.

Команды согласованной установки и безопасных проверок:

```bash
sudo pz story live-begin story_test --yes
sudo pz story live-status story_test
# Ожидаемые отказы без остановки:
sudo pz story live-begin story_test --yes
sudo pz story live-commit story_test --yes
sudo pz story validate clinic_live_001
sudo pz story preview clinic_live_001
```

Checkpoint ДО: `/srv/zomboid/backups/worlds/story_test/world-20261017T100308Z-85664.tar.gz`.
Он сохранён, восстановление не запускалось. Последующий live-commit
пока BLOCKED до проверки содержимого клиентом и согласованного выхода игроков.

## Первый apply-live с реальным клиентом

`pz story scan-player story_test admin --yes` перед применением: complete,
3125 кандидатов, loaded=1157, nil=1968, errors=0, truncated=false;
точный cabinet selector совпал, контейнер пуст. Применено
`pz story apply-live story_test clinic_live_001 --yes`:
`doctor_journal_live=applied`, `medical_cache_live=applied`, complete.
Контейнер ID/StartedAt не менялись, RestartCount=0, OOM=false; ошибок
LIVE_ERROR нет. Повторное применение той же сцены отклонено CLI, exit 2.
`pz save-live` после правок успешен. Сессия остаётся open, applied_scenes=1.

Повторный scan подтвердил два Bandage и один Disinfectant в шкафу.
Записка исчезла из шкафа после чтения: реальный vanilla
ISInventoryPaneContextMenu.onWriteSomething вызывает transferIfNeeded,
поэтому это ожидаемый перенос в инвентарь читателя, а не потеря данных.
Игрок подтвердил наличие записки и читаемую кириллицу — PASS.
Три страницы в UI — **FAIL**: клиент показывал одну страницу.

Причина подтверждена исходниками pinned Build 42.21:
`media/lua/shared/TimedActions/ISWriteSomething.lua`, start, передаёт
`item:getPageToWrite()` в ISUIWriteJournal; runtime задавал лишь
`setNumberOfPages()`. Исправление задаёт также setPageToWrite и добавляет
API preflight/regression assertions. Исправление ещё **не установлено**
в работающий сервер: нужен новый согласованный restart без игроков.

Для повторного теста подготовлен новый `clinic_live_pages_002` только
с одной запиской. Исходная записка и медикаменты сохраняются. Новая сцена
ещё не отправлялась. Две игровые проверки по-прежнему обязательны:
навигация всех трёх страниц после установки, затем сохранность/повторный
вход и окончательный checkpoint ПОСЛЕ. Восстановление не выполняется.

Исправление pageToWrite проверено в exact-game Kahlua live и legacy runtime harness: PASS. Python live tests: PASS. Клиентская навигация после установки по-прежнему BLOCKED.
