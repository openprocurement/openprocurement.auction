*** Keywords ***
Переключитись на учасника
    [Arguments]    ${user_id}
    Switch Browser   ${user_id}
    ${CURRENT_USER}=  set variable    ${user_id}
    Set Global Variable   ${CURRENT_USER}

Підготувати клієнт для користувача
    [Arguments]    ${user_id}
    Open Browser  http://prozorro.org/    ${BROWSER}  ${user_id}
    Set Window Position   @{USERS['${user_id}']['position']}
    Set Window Size       @{USERS['${user_id}']['size']}

Залогуватись користувачем
    [Arguments]    ${user_id}
    Go to       ${USERS['${user_id}']['login_url']}
    Wait Until Page Contains       Дякуємо за використання нашої системи електронних закупівель
    Highlight Elements With Text On Time          Так
    Capture Page Screenshot
    Click Element              confirm
    Wait Until Page Contains   Ви зареєстровані як учасник. Очікуйте старту аукціону.
    Highlight Elements With Text On Time     Ви зареєстровані як учасник. Очікуйте старту аукціону.
    Page Should Contain        Очікування
    Capture Page Screenshot

Перевірити інформацію по себе
    Page Should Contain        до вашої черги
    Page Should Contain        Ви
    Highlight Elements With Text On Time    Ви


Поставити мінімально допустиму ставку
    Wait Until Page Contains Element    id=max_bid_amount_price
    ${last_amount}=     Get Text    id=max_bid_amount_price
    Highlight Elements With Text On Time    ${last_amount}
    Поставити ставку   ${last_amount}   Заявку прийнято


Поставити низьку ціну в ставці
    [Arguments]    ${extra_amount}
    Wait Until Page Contains Element    id=max_bid_amount_price
    ${last_amount}=     Get Text    id=max_bid_amount_price
    Highlight Elements With Text On Time    ${last_amount}
    ${last_amount}=     convert_amount_to_number    ${last_amount}
    ${last_amount}=    Evaluate      ${last_amount}-${extra_amount}
    Поставити ставку   ${last_amount}   Надто низька заявка

Поставити ставку
    [Arguments]    ${amount}  ${msg}
    Set To Dictionary    ${USERS['${CURRENT_USER}']}   last_amount=${amount}
    ${x}=  Convert To String  ${USERS['${CURRENT_USER}']['last_amount']}
    Input Text      id=bid-amount-input      ${x}
    sleep  1s
    Capture Page Screenshot
    Highlight Elements With Text On Time    Зробити заявку
    Click Element                id=place-bid-button
    Wait Until Page Contains     ${msg}    10s
    Highlight Elements With Text On Time    ${msg}
    Capture Page Screenshot

Відмінитити ставку
    Highlight Elements With Text On Time   Відмінити заявку
    Click Element                id=cancel-bid-button
    Wait Until Page Contains     Заявку відмінено      10s
    Highlight Elements With Text On Time    Заявку відмінено
    Capture Page Screenshot

Вибрати кориcтувача, який може поставити ставку
    :FOR    ${user_id}    IN    @{USERS}
    \   Переключитись на учасника   ${user_id}
    \   ${status}	${value}=    Run Keyword And Ignore Error   Page Should Contain  до закінчення вашої черги
    \   Run Keyword If    '${status}' == 'PASS'    Exit For Loop

Перевірити чи ставка була прийнята
    Page Should Contain   ${USERS['${CURRENT_USER}']['last_amount']}
    Highlight Elements With Text On Time   ${USERS['${CURRENT_USER}']['last_amount']}


