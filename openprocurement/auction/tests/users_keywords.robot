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
    Wait Until Page Contains   Sunteți înregistrat ca ofertant. Aștepați pâna licitația începe.
    Highlight Elements With Text On Time     Sunteți înregistrat ca ofertant. Aștepați pâna licitația începe.
    Page Should Contain        Așteptare
    Capture Page Screenshot

Перевірити інформацію по себе
    Page Should Contain        pâna la rândul Dvs.
    Page Should Contain        Dvs.
    Highlight Elements With Text On Time    Dvs.


Поставити максимально допустиму ставку
    Wait Until Page Contains Element    id=max_bid_amount_price
    ${last_amount}=     Get Text    id=max_bid_amount_price
    Highlight Elements With Text On Time    ${last_amount}
    Поставити ставку   ${last_amount}   Oferta a fost plasată


Поставити велику ціну в ставці
    [Arguments]    ${extra_amount}
    Wait Until Page Contains Element    id=max_bid_amount_price
    ${last_amount}=     Get Text    id=max_bid_amount_price
    Highlight Elements With Text On Time    ${last_amount}
    ${last_amount}=     convert_amount_to_number    ${last_amount}
    ${last_amount}=    Evaluate      ${last_amount}+${extra_amount}
    Поставити ставку   ${last_amount}   Valoare prea mare a ofertei

Поставити ставку
    [Arguments]    ${amount}  ${msg}
    Set To Dictionary    ${USERS['${CURRENT_USER}']}   last_amount=${amount}
    ${input_amount}=   Convert To String  ${amount}
    Input Text      id=bid-amount-input      ${input_amount}
    sleep  1s
    Capture Page Screenshot
    Highlight Elements With Text On Time    Înnaintează oferta
    Click Element                id=place-bid-button
    Wait Until Page Contains     ${msg}    10s
    Highlight Elements With Text On Time    ${msg}
    Capture Page Screenshot

Відмінитити ставку
    Highlight Elements With Text On Time   Anulează oferta.
    Click Element                id=cancel-bid-button
    Wait Until Page Contains     Oferta a fost anulată      10s
    Highlight Elements With Text On Time    Oferta a fost anulată
    Capture Page Screenshot

Вибрати кориcтувача, який може поставити ставку
    :FOR    ${user_id}    IN    @{USERS}
    \   Переключитись на учасника   ${user_id}
        \   ${status}	${value}=    Run Keyword And Ignore Error   Page Should Contain  până se sfârșește rândul Dvs.
    \   Run Keyword If    '${status}' == 'PASS'    Exit For Loop

Перевірити чи ставка була прийнята
    Page Should Contain   ${USERS['${CURRENT_USER}']['last_amount']}
    Highlight Elements With Text On Time   ${USERS['${CURRENT_USER}']['last_amount']}


