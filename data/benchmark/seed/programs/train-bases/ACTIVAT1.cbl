       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACTIVAT1.
      * CARD ACTIVATION CONSENT WINDOW (30 DAYS -> OTP, 7WD CLOSE)
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-DAYS-SINCE-ISSUE       PIC 9(4) VALUE ZERO.
       01  WS-ACTIVATED              PIC X(1) VALUE 'N'.
       01  WS-CONSENT-DAYS           PIC 9(4) VALUE ZERO.
       01  WS-ACTION                 PIC X(8) VALUE SPACES.
       01  WS-RPT-HEADING            PIC X(27)
           VALUE 'CARD ACTIVATION AUDIT'.
       01  WS-PAGE-NBR               PIC 9(6) VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-DAYS-SINCE-ISSUE
           ACCEPT WS-ACTIVATED
           ACCEPT WS-CONSENT-DAYS
           PERFORM 2000-DECIDE
           DISPLAY 'ACTION: ' WS-ACTION
           STOP RUN.
       2000-DECIDE.
           IF WS-ACTIVATED = 'Y'
              MOVE 'NONE' TO WS-ACTION
           ELSE
              IF WS-DAYS-SINCE-ISSUE > 30
                 IF WS-CONSENT-DAYS > 7
                    MOVE 'CLOSE' TO WS-ACTION
                 ELSE
                    MOVE 'SEEKOTP' TO WS-ACTION
                 END-IF
              ELSE
                 MOVE 'WAIT' TO WS-ACTION
              END-IF
           END-IF.
