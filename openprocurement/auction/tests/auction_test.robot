*** Settings ***

Documentation  A test suite with a single test for valid login. This test has
...            a workflow that is created using keywords from the resource file.
Suite setup    Підготовка тесту
Suite teardown    Close all browsers
Resource       resource.robot


*** Test Cases ***

Перевірка логіну
    Залогуватись користувачами

1-ша пауза
    Дочекатистись паузи перед 1 раундом
    Дочекатистись завершення паузи перед 1 раундом

Поставити ставку
    Дочекатистись учасником початку стадії ставок
    Поставити максимально допустиму ставку
    Відміитити ставку
    Поставити максимально допустиму ставку
    Дочекатистись учасником закінчення стадії ставок

Завершення аукціону
    Дочекатистись до завершення аукціону без розкриття імен учасників   15 min
    Дочекатистись до завершення аукціону
