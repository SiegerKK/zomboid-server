# Story Director: фактическая приёмка PR #8

Дата: 2026-10-17 UTC. Этап: runtime `f81f39e` установлен с разрешения владельца;
live-begin завершён, ожидается подключение клиента для первого apply-live. Все игровые испытания — только story_test.
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
| apply-live/live-status, записка и медикаменты | VPS + клиент | BLOCKED | После установки, baseline checkpoint и live-скана шкафа |
| Повторная сцена/выход-вход/нет дубликатов | VPS + клиент | BLOCKED | Сначала фактическое применение и подтверждение игроком |
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
