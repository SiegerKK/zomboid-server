# A-Life вместо TLOU/Forge, story_test

Владелец разрешил заменить TLOU/Forge на A-Life и дополнительно отключить
SiegerRadio. SiegerAdmin остаётся выключенным. Игра 42.22.2, тот же мир,
карта, профиль Sandbox и сохранения; без reboot/restore/reset.

Новый профиль `alife`: ZombieBuddy, StarlitLibrary, Viewpoint,
ImmersiveDriving, ProjectALifeNPCs (Workshop 3803984183).
Не содержит TLOU, ZomboidForge, Bandits или Radio.
Ранее выбранные профили остаются в репозитории без изменений.

Подтверждён конфликт исходников Forge/A-Life: Forge.IsZombieValid допускает
тело с ProjectALifeOwned=true; core кэширует validity callback и применяет
визуальные/поведенческие обработчики. A-Life рекомендует исключать такие
тела. Вместо непроверенного адаптера Forge отключён по решению владельца.
В A-Life 1.5.1 найден частичный адаптер ImmersiveDriving; камера/Java/анимации
не заявлены авторами как полностью проверенные. Для 42.22.2 нужна игровая
приёмка: Workshop-описание заявляет B42.21, mod.info имеет минимум 42.21.0.
Обязательных require и отдельных Java JAR у проверенной копии A-Life нет.

Установка через единый pz, только при пустом сервере:

```bash
sudo pz stop --yes
sudo pz save story_test --yes
# exact CI-passed deploy
sudo pz story alife-install story_test --yes
sudo pz start story_test
sudo pz story engine-info story_test
```

Установщик проверяет stop, active world, data mount, Admin OFF, свежий
SHA-verified cold backup и точное совпадение прежнего профиля с источником.
Сохраняет старые profile/mods/snapshot/radio markers в profile-history.
Скачивает новый Workshop snapshot, проверяет фактический A-Life Mod ID,
зависимости и отсутствие неожиданного Java-компонента. При ошибке чинит
только конфигурационную транзакцию, не восстанавливает и не удаляет save.
Радио выключается удалением enable marker, его исходники, музыка и игровые
данные не удаляются. TLOU Sandbox keys сохраняются как данные; активного
обработчика TLOU нет. Существующие заражённые могут потерять специфические
TLOU-эффекты/визуал; массовой зачистки существующих сущностей нет.

Клиентам: подписаться на Workshop 3803984183, дождаться скачивания,
отключить TLOU Infected, ZomboidForge, SiegerAdmin и SiegerRadio.
Оставить ZombieBuddy/StarlitLibrary/Viewpoint/ImmersiveDriving/A-Life,
играть на 42.22.2. Никаких отдельных PowerShell/Java installers для A-Life.
Клиентские моды перед входом должны совпадать с серверным набором.

Автотесты: profile identity/forbidden mods, stop gate, безопасный download
failure и успешная смена профиля с Radio OFF без изменения save sentinel.
Обычный вход, NPC, бой/вождение и два клиента требуют игровой приёмки.
Факт скачивания или успешный старт не доказывает корректный NPC multiplayer.
