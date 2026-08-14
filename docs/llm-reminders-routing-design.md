# LLM Reminders routing design

## Understanding summary

- Assist-фразы про напоминания не должны попадать во встроенный `HassStartTimer`
  или другой local intent.
- Триггер двуязычный: он распознаёт русские формы `напомин…` и английские
  формы `remind…`/`reminder…` как отдельные слова, с границами слова.
- В область маршрутизации входят все операции с напоминаниями: создание,
  просмотр, отмена и изменение.
- Для совпавшей фразы используется conversation agent текущего Assist pipeline
  и исходный `ConversationInput`.
- При отсутствии `device_id`, satellite или при ошибке LLM запрос завершается
  понятной ошибкой; `default_satellite` и native fallback не используются.
- Команды без триггерных слов сохраняют текущую обработку local intents и
  native timers.
- Решение остаётся внутри интеграции и рассчитано на Home Assistant Core
  `2026.8.0+`.

## Accepted scope and assumptions

- Гарантия действует для Assist pipeline с внешним LLM conversation agent
  (текущий сценарий с Gemma). Local-only Home Assistant pipeline остаётся
  штатным исключением Core: Core не передаёт такие запросы во внешние sentence
  triggers, поэтому интеграция не может изменить его поведение без patch Core.
- На одном Home Assistant device используется один Assist Satellite. Это
  позволяет однозначно разрешить target satellite через `device_id`.
- Дополнительная задержка одного вызова conversation agent/LLM приемлема.
- Несколько команд с разными satellite могут выполняться одновременно; общий
  mutable state для маршрутизации не используется.
- Router передаёт исходный текст, `conversation_id`, `Context`, `device_id`,
  `satellite_id`, язык, `agent_id` и `extra_system_prompt`, но не дублирует их
  в собственном хранилище.
- Ошибки озвучиваются на языке текущего Assist pipeline.
- Настроенный `default_satellite` сохраняется для прежних не-голосовых
  сценариев manager, но не используется новым voice router.

## Decision log

1. **Сохранить `prefer_local_intents`.** Обычные команды должны продолжить
   выполняться локально.
2. **Перехватывать формы `напомин…` и `remind…` до local intents.** Это
   предотвращает обработку фразы как `HassStartTimer`.
3. **Использовать sentence trigger с wildcard-текстом.** Так callback получает
   исходный `ConversationInput`, а не только распарсенные slots, и покрывает
   произвольные формулировки.
4. **Вызывать текущий conversation agent через `conversation.async_converse`.**
   Передаются исходные text, conversation/context, device/satellite, language,
   agent id и extra system prompt.
5. **Не использовать satellite fallback в voice path.** Потеря контекста должна
   завершаться fail-closed ошибкой.
6. **Оставить native timers вне триггерных слов.** Native timer behavior не
   меняется для остальных команд.
7. **Не менять Home Assistant Core.** Решение ограничено кодом и тестами
   интеграции; local-only pipeline явно не входит в гарантию.

## Final design

### Registration and lifecycle

1. Интеграция добавляет отдельный `conversation_router` module.
2. При `async_setup_entry` после успешного запуска manager router один раз
   вызывает conversation manager `register_trigger` и сохраняет returned
   unregister callback в отдельном ключе `hass.data`.
3. При reload/unload callback снимается ровно один раз; повторная загрузка не
   создаёт дубликатов. После снятия trigger manager продолжает доставлять уже
   сохранённые напоминания, но новые voice requests не принимаются.

### Trigger matching

- Шаблоны содержат альтернативы русских и английских reminder-форм и wildcard
  участки до/после ключевого слова.
- Ключевые слова являются отдельными literal tokens: произвольные совпадения
  внутри других слов не считаются trigger match.
- Matching нечувствителен к регистру и обычной пунктуации. Callback повторно
  проверяет исходный текст перед маршрутизацией.
- Positive cases включают формы в начале, середине и конце фразы; negative
  cases включают обычные команды вроде `включи свет` и `поставь таймер`.

### Routing callback

1. Callback получает `ConversationInput` и `RecognizeResult`.
2. Если `user_input.device_id` отсутствует, он сразу возвращает локализованную
   ошибку и не вызывает LLM.
3. Иначе callback вызывает `conversation.async_converse`, передавая исходные
   `text`, `conversation_id`, `context`, `device_id`, `satellite_id`,
   `language`, `agent_id` и `extra_system_prompt`.
4. LLM agent вызывает существующие `llm_reminders` tools. Tool получает
   `device_id`; manager разрешает единственный Assist Satellite этого device.
5. Speech из `ConversationResult` возвращается в исходный Assist pipeline.
6. При отсутствии satellite, исключении agent или пустом speech callback
   возвращает стабильную локализованную ошибку. Он не возвращает `None`, чтобы
   pipeline не переходил к native intent.

### Other commands and failure behavior

- Фразы без reminder-форм проходят существующую последовательность Assist;
  `prefer_local_intents` и native timers остаются включёнными.
- Ошибки tools (неполное время, неоднозначная отмена и т. п.) передаются speech
  conversation agent без повторной попытки native timer.
- Каждая команда использует только собственный `ConversationInput`; shared
  state для выбора satellite запрещён.
- Local-only pipeline остаётся штатным исключением Core и не является частью
  гарантии интеграционного router.

## Verification and acceptance checks

### Automated tests

- Matching русских форм `напомни`, `напомнить`, `напоминание` и английских
  `remind`, `reminder` в разных позициях.
- Regression для `включи свет` и обычного `поставь таймер`.
- Сохранение всех полей `ConversationInput` при вызове `async_converse`.
- Fail closed для отсутствующего device, отсутствующего satellite, исключения
  agent и пустого response; `default_satellite` не используется.
- Lifecycle регистрации/unregister и отсутствие дубликатов.
- Два одновременных callback с разными `device_id` не смешивают маршруты.

### Repository checks

```powershell
python -m pytest tests
python -m compileall -q custom_components\llm_reminders
```

Реальный Assist/Gemma прогон выполняется вручную в Home Assistant, поскольку
репозиторий не содержит runtime Home Assistant.

## Rejected alternatives

- **Явный конечный список полных предложений:** не покрывает произвольный
  порядок слов и новые грамматические формы.
- **Перехват только `HassStartTimer`:** не маршрутизирует список/отмену/изменение
  и не гарантирует покрытие всех фраз с reminder-словом.
- **Удаление native timer handler:** не является поддержанной настройкой и
  может дать `UnknownIntent`, а не LLM fallback.
- **Последний активный или default satellite для voice path:** race condition и
  риск доставки не тому устройству.
- **Обёртка над agent или patch Assist pipeline:** технически дают полный
  контроль, но требуют отдельной настройки/собственного HA Core и нарушают
  выбранное ограничение.

## References

- [Conversation sentence trigger](https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/components/conversation/trigger.py)
- [Conversation agent manager](https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/components/conversation/agent_manager.py)
- [Conversation models and LLM context](https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/components/conversation/models.py)
- [LLMContext](https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/helpers/llm.py)
- [Assist pipeline routing](https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/components/assist_pipeline/pipeline.py)
- [Template sentence syntax and wildcard lists](https://developers.home-assistant.io/docs/voice/intent-recognition/template-sentence-syntax/)
