# Модпак со скриншота — Project Zomboid Build 42.21.0

Список из 12 пунктов. **Статус: staged, не установлен и не проверен в игре.** Перед запуском сделайте холодный backup нового мира, disposable тестовый запуск и проверьте версии/зависимости. Моды для 42.20 могут быть несовместимы с 42.21.0.

| Мод | Внутренний Mod ID | Workshop ID | План |
| --- | --- | --- | --- |
| ZombieBuddy | ZombieBuddy | 3619862853 | Сервер; проверить Java agent на Linux и security |
| Bandits | Bandits2 | 3268487204 | **Отключён:** конфликт с TLOU; НЕ устанавливать |
| Bandits Creator | BanditsCreator | 3469292499 | **Отключён:** вместе с Bandits; НЕ устанавливать |
| Viewpoint | Viewpoint | 3809306528 | Сервер; проверить dedicated MP |
| Immersive Driving | ImmersiveDriving | 3817413313 | Сервер + клиент; совместная езда |
| [B42.20] TLOU Infected | TLOU_Infected_42_20 | 3776164832 | Сервер; проверить B42.21 |
| [B42.20] Zomboid Forge | ZomboidForge | 3776274080 | Сервер; проверить B42.21 |
| Starlit Library | StarlitLibrary | 3378285185 | Библиотека зависимостей |
| Viewpoint - Barricade Fix | ViewpointBarricade | 3815033191 | Кандидат client-only, проверить |
| Viewpoint Immersive Camera Motion | ViewpointBodycam | 3818432217 | Кандидат client-only, проверить |
| Viewpoint: Living Props | ViewpointLivingProps | 3816442251 | Client-only по автору |
| Death Cam for Viewpoint | ViewpointDeathCam | 3816588758 | ID подтверждён Workshop + mod.info; Java client-side, MP требует проверки |

В `config/mods.env` внесены 6 модов серверного набора. Bandits2 и BanditsCreator удалены из активации в пользу TLOU. Четыре Camera/Viewpoint addons находятся в документации, не активируются сервером без проверки. Не принимайте порядок таблицы за гарантированный порядок зависимостей: проверьте документацию Workshop и mod.info.

## Последовательность тестов

1. Если ванильный сервер работает, остановить штатно (только при отсутствии игроков) и выполнить cold backup. Не удалять мир/volume.
2. Сверить каждый URL Steam Workshop, текущую поддержку Build 42.21 и зависимости. ZombieBuddy требует отдельного внимания к Java-agent и Linux.
3. Поднять тестовый мир с отдельным data volume, не используя production save. Установить набор core mods, проверить server log и предметы/NPC, тест соединения двух клиентов.
4. Добавлять клиентские дополнения на компьютеры игроков, а не автоматически в server JVM. Для неизвестного Death Cam установить ID из реального Steam Workshop и `mod.info`, не угадывать.
5. Проверить совместную поездку, TLOU infected, расход памяти; только после успешного теста применять изменения к production. Модификации с 42.20 не активировать, если обнаружены ошибки совместимости.

Никакие пароли/данные пользователей не хранить в GitHub.

## Выявленный конфликт Bandits / TLOU

В обсуждениях TLOU зафиксированы случаи, когда Bandits NPC превращались в вооружённых infected/Clicker; у Bandits NPC используются zombie-based объекты, изменяемые TLOU. Ранее существовал compatibility patch Workshop `3564614319`, но он заброшен. Поэтому приоритет — **TLOU**, и **Bandits2 (3268487204)** вместе с **BanditsCreator (3469292499)** исключены из рабочего набора. Это решение на уровне конфигурации; VPS автоматически не обновлён. На тестовом мире проверить отсутствие модов и зависимых скриптов в папках и списках `Mods`, а также корректную загрузку TLOU.

Внимание: альтернативная версия TLOU для SP/MP Workshop `3781448194`, Mod ID `TLOU_Infected_MP`, позиционируется как исправляющая синхронизацию в мультиплеере. Её совместимость именно с Build 42.21.0 и вашим сервером ещё не подтверждена. **Не устанавливать одновременно две версии TLOU.** Перед переключением проводить отдельный тест на временном мире.

## Проверка файлов на VPS, 2026-10-16

Все 12 позиций скачаны отдельно для аудита; это не означает активацию на сервере.
Идентификаторы сверены с реальными mod.info. Исправлены исходные соответствия:
Bandits2 = 3268487204, BanditsCreator = 3469292499, StarlitLibrary = 3378285185.
Действует новое решение исключить Bandits/Creator в пользу TLOU; их файлы сохранены
только в /srv/zomboid-mod-audit и не включены в snapshot тестового сервера.

| Mod ID | Подтверждённые require/version в mod.info |
| --- | --- |
| ZombieBuddy | id подтверждён в 41/42; JAR 2.3.4 |
| Viewpoint | ZombieBuddy; versionMin=42.21, versionMax=42.21 |
| ImmersiveDriving | Viewpoint,ZombieBuddy |
| StarlitLibrary | варианты 42, 42.12, 42.13, 42.15; последний versionMin=42.15.0 |
| ZomboidForge | StarlitLibrary; versionMin=42.0; папка 42.20 |
| TLOU_Infected_42_20 | ZomboidForge,StarlitLibrary; versionMin=42.20 |
| Bandits2 | папка 42.21 имеется, но мод исключён из набора |
| BanditsCreator | Bandits2; исключён из набора |
| ViewpointBarricade | Viewpoint; versionMin=42.21 |
| ViewpointBodycam | ZombieBuddy,Viewpoint; versionMin=42.21; loadModAfter=Viewpoint,ProjectViewpointADS |
| ViewpointLivingProps | Viewpoint,ZombieBuddy; versionMin=42.21 |
| ViewpointDeathCam | ZombieBuddy,Viewpoint; versionMin=42.21 |

ZombieBuddy.jar SHA-256: `eb79b9876332010733a8e0d7ce4fe0377846059a9e28859029e2a0fb449f6cf2`.
Viewpoint и ImmersiveDriving, как и четыре дополнения, содержат JAR в
media/java/client; они не должны автоматически исполняться dedicated JVM.
На Linux нужен Java agent ZombieBuddy.jar; Windows DLL не копировать.
Для headless используется policy=deny-new,frontend=console, без allow-all.
Агент передаётся только игровой JVM через entrypoint, не через JAVA_TOOL_OPTIONS,
поскольку launcher также запускает java -version и агент не предназначен для этой проверки.

Изолированный compose.modtest.yaml использует отдельные data/workshop, сеть,
случайные test-секреты, heap 8192m и лимит 12g, без опубликованных портов.
Production по умолчанию использует config/mods.vanilla.env; выбор другого файла
возможен через PZ_MODS_FILE только после проверки и cold backup.
Результаты фактической загрузки и теста восстановления фиксируются отдельно;
одна загрузка Workshop-файлов не подтверждает совместимость.

Первый isolated headless запуск шести модов дошёл до SERVER STARTED и отвечает
через внутренний RCON; OOM и самопроизвольных рестартов нет. В журнале есть
loading StarlitLibrary/ZomboidForge/TLOU_Infected_42_20, loadMods(6 mods).
ZombieBuddy policy=deny-new блокирует Java Viewpoint и ImmersiveDriving из
media/java/client на dedicated: эти графические компоненты не объявляются
исполняющимися на VPS. Клиентам всё равно требуется собственная установка агента.

Имеются дополнительные WARN require для ZomboidForge_ModOptions и поведения
TLOU (General/Runner/Stalker/Clicker/Bloater_behavior). Файлы Behaviors присутствуют
в shared/Behaviors; одного успешного старта недостаточно, чтобы доказать, что все
события infected работают. В vanilla тоже есть ошибки движка/UI/WorldGen;
не следует автоматически приписывать каждую строку ERROR модам.
Пока основной мир vanilla; переключение для MP-теста требует решения владельца.
MP Edition 3781448194 скачивается/проверяется отдельно, в этот запуск не включена.

Источники: [ZombieBuddy](https://steamcommunity.com/sharedfiles/filedetails/?id=3619862853),
[Immersive Driving](https://steamcommunity.com/sharedfiles/filedetails/?id=3817413313),
[Death Cam](https://steamcommunity.com/sharedfiles/filedetails/?id=3816588758),
[Living Props](https://steamcommunity.com/sharedfiles/filedetails/?id=3816442251).
Автор Death Cam указывает client-side исполнение, необходимость server-list для MP
и отсутствие своего MP-теста: это пока клиентский кандидат, а не включённый server mod.
