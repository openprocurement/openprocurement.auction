*** Settings ***
Library        Selenium2Library
Library        Selenium2Screenshots
Library        DebugLibrary
Resource       users_keywords.robot
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

Залогуватись користувачами
    :FOR    ${user_id}    IN    @{USERS}
    \   Переключитись на учасника   ${user_id}
    \   Залогуватись користувачем   ${user_id}
    \   Перевірити інформацію з меню


Перевірити інформацію з меню
    sleep                      1s
    Click Element              id=menu_button
    Wait Until Page Contains   Browser ID
    Highlight Elements With Text On Time    Browser ID
    Wait Until Page Contains   Session ID
    Highlight Elements With Text On Time    Session ID
    Capture Page Screenshot
    Press Key                  xpath=/html/body/div/div[1]/div/div[1]/div[1]/button     \\27
    sleep                      1s


Дочекатистись паузи перед ${round_id} раундом
    Wait Until Page Contains    → ${round_id}    5 min

Дочекатистись завершення паузи перед ${round_id} раундом
    Wait Until Page Does Not Contain    → ${round_id}    5 min


Дочекатистись учасником початку стадії ставок
    [Arguments]    ${timeout}=3 min
    Wait Until Page Contains        до закінчення вашої черги   ${timeout}


Дочекатистись учасником закінчення стадії ставок
    [Arguments]    ${timeout}=3 min
    Wait Until Page Does Not Contain         до закінчення вашої черги   ${timeout}

Дочекатистись до завершення аукціону
    [Arguments]    ${timeout}=5 min
    Wait Until Page Does Not Contain   Очікуємо на розкриття імен учасників.  ${timeout}
    Wait Until Page Contains      Аукціон завершився   ${timeout}

Дочекатистись до завершення аукціону без розкриття імен учасників
    [Arguments]    ${timeout}=10 min
    Wait Until Page Contains      Очікуємо на розкриття імен учасників.  ${timeout}

Перевірити інформацію про тендер
    Page Should Contain   ${TENDER['title']}                    # tender title
    Page Should Contain   ${TENDER['procuringEntity']['name']}  # tender procuringEntity name



