# road_home: фактическое развёртывание, 2026-10-16

## Состояние

Рабочий мир **road_home** запущен в фоне через `sudo pz` на
**62.171.140.149:16261**, Project Zomboid **42.21.0**. Профиль менеджера
`mp-test` означает выбранную SP/MP-редакцию; правила `tlou-coop`.
Сохранения: `/srv/zomboid/worlds/road_home/data`.
Внутренний SERVER_NAME остаётся SiegerZomboid для совместимости менеджера.
Original, legacy data и все прежние backup/тестовые слоты сохранены.

База кода — main `81b18ee524b57b25a230d2699a076817305a11e8`, необходимые
исправления генератора и диагностики оформлены отдельно в **PR #4**.
Точный установленный source commit указан в `/opt/zomboid-server/DEPLOYED_COMMIT`.
Runtime `.env` root:root 600 не перезаписывался; root-owned Bash `pz` доступен
через прежнюю системную символьную ссылку. Reboot и изменения SSH не выполнялись.
SaaS/host Nginx не менялись. Автоматический production deploy не включён.

## Игра и моды

Image закреплён:
`ghcr.io/meshi-team/project-zomboid-server@sha256:45c602cb07a1f4b228eefcf92ed4480cf877c409dcd16f0aaa53432063dd3b56`.
Реальный game log подтвердил version=42.21.0.

| Mod ID | Workshop ID | Проверка |
| --- | --- | --- |
| ZombieBuddy | 3619862853 | Linux agent 2.3.4, прежний проверенный JAR |
| StarlitLibrary | 3378285185 | вариант 42.15, minimum 42.15.0 |
| ZomboidForge | 3776274080 | патч 42.20, minimum 42.0; depends Starlit |
| TLOU_Infected_MP | 3781448194 | minimum 42.20; depends Forge/Starlit |
| Viewpoint | 3809306528 | common/mod.info minimum/maximum 42.21; depends ZombieBuddy |
| ImmersiveDriving | 3817413313 | depends Viewpoint/ZombieBuddy |

Все шесть скачаны, реально загружены сервером и проверены по mod.info.
`TLOU_Infected_42_20 / 3776164832`, Bandits и Bandits Creator в этом snapshot
не присутствуют и не активированы. Клиентские camera addons не добавлялись.
Старый профиль `tlou` не подменялся, чтобы не менять существующий original.
Workshop смонтирован read-only; полный file SHA-256 manifest после тестов
совпадает. Steam metadata MP-редакции взята из её настоящего SteamCMD-download,
а не придумана. Мир не получает unattended mod updates.

Источник выбора SP/MP: [Workshop автора](https://steamcommunity.com/sharedfiles/filedetails/?id=3781448194),
[Forge patch](https://steamcommunity.com/sharedfiles/filedetails/?id=3776274080),
[Starlit](https://steamcommunity.com/workshop/filedetails/?id=3378285185).
Заявления автора о сетевых исправлениях не заменяют двухклиентский тест.

## Проверенные Sandbox и заражённые

Полный `config/presets/TLOU_November_12Months.lua` построен из ванильного
VERSION=6 экспорта, созданного **тем же pinned image**; provenance manager-a
содержит совпадающий digest. Внутренний image helper-default оказался VERSION=5:
номер не менялся вручную и чужой B41-шаблон не использовался.
Исправлены поддержка quoted PZ_IMAGE и inline type/default в Workshop schema.

Production preset сгенерирован **без** unverified flag. Отдельная предварительная
кандидатная генерация с этим флагом использовалась исключительно для теста
инициализаторов в disposable контейнере без сети, без подключения игровых data.
Оба режима server/client дали одинаковый ожидаемый реестр. После этого строгая
генерация требует точные source/test hashes в `.sources.json`.
Генератор не исполняет Workshop Lua. Изменённый source или новый Lua overlay
должны пройти новый аудит; root runtime проверка и CI не отключаются.

Сравнены **45 ключей** live Sandbox-файла с обоими intent TSV; всё совпало.
Read-only server-side Lua-аудит внутри настоящей игры дополнительно подтвердил:

- календарь **1993-11-30**; StartMonth=11, StartDay=30;
- DayLength=6 = **3 реальных часа**; TimeSinceApo=13 = **12 месяцев**;
- Temperature=2 Cold, Rain=4; холодный климат, не принудительно постоянная температура;
- PvP=true, PauseEmpty=true, Open=true, Public=false, максимум 6 игроков;
- XP GlobalToggle=false; Strength/Fitness ×10, Mechanics ×4, Woodwork ×5;
- AmmoLootNew=1.4, RangedWeaponLootNew=1.0; остальной loot по полному intent;
- native ZombieConfig.PopulationMultiplier=**0.3**, respawn hours/multiplier=0;
- общая популяция **не отключена**: Zombies не None, эффективный native multiplier положителен;
- точный живой реестр: **TLOU_Runner=560, TLOU_Stalker=330, TLOU_Clicker=110**;
- **REGISTRY_COUNT=3, NORMAL_TYPE_PRESENT=false**, Bloater не зарегистрирован;
- `TLOU_infected.VanillaSpawn=false`, VanillaSpawnWeight=0;
- `HideIndoors=true`, OnlyUnexplored=false, WanderAtNight=true;
- callbacks HideIndoors реально присоединены к Stalker и Clicker.

В этой версии у Forge нет sandbox-option ZomboidSpawn, и guarded AddZomboids
при nil не вызывается. MP fork имеет собственный обычный тип TLOU_Vanilla,
который явно выключен. Не добавлялись неизвестные Forge-ключи и не отключалась
вся базовая популяция ради исключения обычных зомби.

Веса дают 56/33/11 процентов среди зарегистрированных типов. Forge назначает тип
после создания базового IsoZombie, поэтому краткая переходная модель при spawn
возможна. TimeSinceApo не подменяет внутренний daysSurvived мода; здесь типы
включены явными весами. HideIndoors задаёт стремление к зданиям, а не гарантирует
изменённую долю спавна внутри каждого дома. Эффект проверяется игроками.

Первый запуск имел сообщения AdvancedAnimator о 23 отсутствующих необязательных
AnimSets/actiongroups каталогах модов. Созданы только пустые каталоги, без
изменения единого Workshop-файла. На последующих запусках этих исключений 0.
Прежние vanilla UI/WorldGen и client-only ModOptions предупреждения не скрывались;
их наличие не выдаётся за проверку сетевой игры.

## Сохранение, восстановление и ресурсы

Перед переключением RCON показал 0 игроков. Original сохранён и остановлен
с ExitCode=0. Cold backup:
`backups/worlds/original/world-20261016T183712Z-26742.tar.gz`, SHA-256 OK;
распаковка `/var/tmp/pz-original-pre-road-home.O9Q0iI` проверена.

Новый road_home прошёл save-live, проверку pause, полный stop (PID=0), offline save,
load в **новый** `road_home_restore_check` и реальный boot восстановленной копии.
Архив: `backups/worlds/road_home/world-20261016T184755Z-29734.tar.gz`.
SHA-256 OK, все **50 файлов** после распаковки совпали с архивом по SHA-256.
Восстановленный сервер прошёл тот же runtime-аудит Sandbox/типов/секретов,
затем штатно остановлен. Рабочий road_home снова запущен и проверен.
Ни один старый слот или Docker volume не удалялся.

PAUSE_EMPTY проверен двумя save при 0 игроков с интервалом 35 секунд:
SHA-256 map_t.bin не изменился. Stop отдельно подтвердил Running=false/PID=0.
Heap 8192m, memory limit 12 GiB, фактический RAM около 9.24 GiB;
OOM=false, RestartCount=0. Native fps=105 при нуле игроков — idle sample,
не обещание производительности при боях. Секреты в текущих Docker logs не найдены.

Выполнены bash syntax, sudo tests/smoke.sh, tests/tlou_audit.sh,
tests/test_generate_tlou_preset.py, tests/test_tlou_source_contract.py с настоящим
snapshot, isolated Lua registry/syntax tests и Compose проверки PZ/modtest/SaaS.
CI code commits PR #4 прошёл. Offsite encrypted backup пока отсутствует:
описанные копии локальные на VPS.

## Сеть и подключение

Проверены внешние реальные A2S UDP16261 и RakNet UDP16262 ответы.
A2S players=0/max=6/password_required=0. Последний разовый RTT 811/100 ms:
это не усреднённый игровой ping, jitter/loss ещё нужно измерить из двух городов.
RCON 27015/TCP не публикуется: Docker binding только UDP16261/16262,
внешние служебные TCP27015/5432/6379/2375/2376/18080 не отвечают.
SSH22 доступен. Внешняя IPv6 проверка недоступна из локальной сети без IPv6 route.

1. У обоих клиентов должна быть **Build 42.21.0** и совпадающие Workshop-моды.
2. Для Java-компонентов ZombieBuddy/Viewpoint/Driving выполнить
   [клиентскую установку ZombieBuddy по инструкции автора](https://github.com/zed-0xff/ZombieBuddy).
   На VPS установлен Linux agent; локальные игровые файлы клиентов не менялись.
   Client Java модули не включаются автоматически в dedicated JVM.
3. Project Zomboid → Join → добавить IP **62.171.140.149**, порт **16261**.
   Server password оставить пустым. Выбрать личные игровые username/password;
   Open=true разрешает регистрацию. Для direct UDP проверки Steam Relay OFF.
4. Выбрать одинаковый стартовый город и подтвердить совместную игру.
   Приватный admin password не раздавать. После первого входа kyrylo его роль
   можно отдельно выдать через `sudo pz admin grant kyrylo`.

Два клиента ещё должны проверить авторизацию/модовые checksum, одинаковые типы
заражённых и damage, поведение в десяти домах против улиц, доступность патронов,
совместную езду/смену водителя, rejoin и сохранение персонажей. При 0 игроков
невозможно доказать отсутствие сетевой рассинхронизации. DoLuaChecksum=true и
SteamVAC=true сохранены; защита не отключалась ради устранения ошибок.
