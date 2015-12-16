*** Settings ***
Library        Selenium2Library
Library        Selenium2Screenshots
Library        DebugLibrary
Library        openprocurement.auction.tests.service_keywords

*** Variables ***
${USERS}
${BROWSER}       chrome

*** Keywords ***
Підготовка тесту
    Отримати вхідні дані
    :FOR    ${user_id}    IN    @{USERS}
    \   Підготувати клієнт для користувача   ${user_id}

Отримати вхідні дані
    ${TENDER}=  prepare_tender_data
    Set Global Variable   ${TENDER}
    ${USERS}=  prepare_users_data   ${TENDER}
    Set Global Variable   ${USERS}

Підготувати клієнт для користувача
    [Arguments]    ${user_id}
    Open Browser  http://prozorro.org/    ${BROWSER}  ${user_id}
    Set Window Position   @{USERS['${user_id}']['position']}
    Set Window Size       @{USERS['${user_id}']['size']}

Залогуватись користувачами
    :FOR    ${user_id}    IN    @{USERS}
    \   Switch Browser   ${user_id}
    \   Залогуватись користувачем   ${user_id}
    \   Перевірити інформацію з меню

Залогуватись користувачем
    [Arguments]    ${user_id}
    Go to       ${USERS['${user_id}']['login_url']}
    Page Should Contain        Дякуємо за використання нашої системи електронних закупівель
    sleep                      1
    Capture Page Screenshot
    Click Element              confirm
    Wait Until Page Contains   Ви зареєстровані як учасник. Очікуйте старту аукціону.
    Page Should Contain        Очікування
    Capture Page Screenshot

Перевірити інформацію з меню
    sleep                      1
    Click Element              id=menu_button
    Wait Until Page Contains   Browser ID
    Wait Until Page Contains   Session ID
    Capture Page Screenshot
    sleep                      1
    Press Key                  xpath=/html/body/div/div[1]/div/div[1]/div[1]/button     \\27
    sleep                      1


Дочекатистись паузи перед ${round_id} раундом
    Wait Until Page Contains    → ${round_id}    5 min


Дочекатистись завершення паузи перед ${round_id} раундом
    Wait Until Element Does Not Contain    → ${round_id}    5 min


Перевірити інформацію по себе
    Page Should Contain        до вашої черги
    Page Should Contain        Ви
    sleep                      1

Дочекатистись учасником початку стадії ставок
    [Arguments]    ${timeout}=2 min
    Wait Until Page Contains        до закінчення вашої черги   ${timeout}


Дочекатистись учасником закінчення стадії ставок
    [Arguments]    ${timeout}=2 min
    Wait Until Element Does Not Contain         до закінчення вашої черги   ${timeout}

Дочекатистись до завершення аукціону
    [Arguments]    ${timeout}=5 min
    Wait Until Element Does Not Contain   Очікуємо на розкриття імен учасників.
    Wait Until Page Contains      Аукціон завершився   ${timeout}

Дочекатистись до завершення аукціону без розкриття імен учасників
    [Arguments]    ${timeout}=10 min
    Wait Until Page Contains      Очікуємо на розкриття імен учасників.  ${timeout}

Поставити максимально допустиму ставку
    Wait Until Page Contains Element    id=max_bid_amount
    ${max_bid_amount}=      Get Text    id=max_bid_amount
    Input Text      id=bid-amount-input     ${max_bid_amount}
    sleep  1
    Capture Page Screenshot
    Click Element                id=place-bid-button
    sleep                        1
    Wait Until Page Contains     Заявку прийнято
    Capture Page Screenshot

Відміитити ставку
    Click Element                id=cancel-bid-button
    Wait Until Page Contains     Заявку відмінено
    Capture Page Screenshot      auction_bid_canceled.jpg