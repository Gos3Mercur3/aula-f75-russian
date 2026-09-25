name: Не установилось / не выглядит по-русски
about: Отчёт об установке. Заполните пункты 1–3, иначе помочь невозможно.
labels: bug
body:
- type: markdown
  attributes:
    value: |
      Русский ставится заменой **одного** файла. Если «не сработало» — почти всегда одна из трёх причин, и все они видны за 20 секунд. Заполните, что ниже, и я скажу, какая у вас.
- type: dropdown
  id: model
  attributes:
    label: Модель
    options: [AULA F75, F75 Pro, F75 Max, F87, F99, другая]
    multiple: false
- type: dropdown
  id: from
  attributes:
    label: Скачали откуда
    options: [Releases → v1.0.1, v1.0.0 (устаревший, там нерабочий установщик), не знаю]
    multiple: false
- type: textarea
  id: sizes
  attributes:
    label: |
      Что напечатал УСТАНОВИТЬ.bat в блоке «Проверка»
      (или вывод этой команды — вставьте как есть)
      dir "%ProgramFiles(x86)%\AULA\F75\Text\*\text.xml"
    value: |
      Text\en\text.xml      23302 байт
      Text\sc\text.xml      23302 байт
      Text\Korean\text.xml  23302 байт
    render: text
- type: dropdown
  id: sizes-ok
  attributes:
    label: Все файлы одного размера (23302)?
    options: [да, нет, часть файлов 24544, не знаю]
    multiple: false
- type: checkboxes
  id: steps
  attributes:
    label: Что уже пробовали
    options:
      - label: распаковали архив ЦЕЛИКОМ, батник рядом с text_ru.xml
      - label: запускали правой кнопкой «от имени администратора»
      - label: закрыли программу полностью через трей (крестик не считается)
      - label: проверили VirtualStore (команда ниже → True значит Windows спрятала запись)
        `test-path "$env:LOCALAPPDATA\VirtualStore\Program Files (x86)\AULA\F75"`
- type: textarea
  id: what
  attributes:
    label: Что видите вместо русского
    description: Скриншот тоже можно сюда вставить.
    placeholder: Например: «надписи стали квадратами» / «всё осталось по-английски» / «окно закрылось мгновенно»
