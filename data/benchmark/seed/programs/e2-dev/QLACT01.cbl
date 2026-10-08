       IDENTIFICATION DIVISION.
       PROGRAM-ID. QLACT01.
      * INACTIVE NEW CARD - CONSENT OR CLOSE
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CARD-ACTIVE            PIC X(1) VALUE 'N'.
       01  WS-DAYS-SINCE-ISSUE       PIC 9(4) VALUE ZERO.
       01  WS-OTP-CONSENT            PIC X(1) VALUE 'N'.
       01  WS-WDAYS-SINCE-ASK        PIC 9(3) VALUE ZERO.
       01  WS-STEP                   PIC X(10) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CARD-ACTIVE
           ACCEPT WS-DAYS-SINCE-ISSUE
           ACCEPT WS-OTP-CONSENT
           ACCEPT WS-WDAYS-SINCE-ASK
           PERFORM 2000-DECIDE
           DISPLAY 'STEP: ' WS-STEP
           STOP RUN.
       2000-DECIDE.
           MOVE 'NONE' TO WS-STEP
           IF WS-CARD-ACTIVE = 'N'
              IF WS-DAYS-SINCE-ISSUE > 30
                 EVALUATE TRUE
                    WHEN WS-OTP-CONSENT = 'Y'
                       MOVE 'ACTIVATE' TO WS-STEP
                    WHEN WS-WDAYS-SINCE-ASK > 7
                       MOVE 'CLOSEFREE' TO WS-STEP
                    WHEN OTHER
                       MOVE 'ASKOTP' TO WS-STEP
                 END-EVALUATE
              END-IF
           END-IF.
