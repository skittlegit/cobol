       IDENTIFICATION DIVISION.
       PROGRAM-ID. QLDOR04.
      * UNUSED CARD - NOTICE, CLOSE, AND CIC UPDATE
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-MONTHS-UNUSED          PIC 9(3) VALUE ZERO.
       01  WS-NOTICE-SENT            PIC X(1) VALUE 'N'.
       01  WS-DAYS-SINCE-NOTICE      PIC 9(3) VALUE ZERO.
       01  WS-REPLY                  PIC X(1) VALUE 'N'.
       01  WS-DUES                   PIC 9(9)V99 VALUE ZERO.
       01  WS-STEP                   PIC X(10) VALUE SPACES.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-MONTHS-UNUSED
           ACCEPT WS-NOTICE-SENT
           ACCEPT WS-DAYS-SINCE-NOTICE
           ACCEPT WS-REPLY
           ACCEPT WS-DUES
           PERFORM 2000-DORMANCY
           DISPLAY 'STEP: ' WS-STEP
           STOP RUN.
       2000-DORMANCY.
      * CLOSING THE ACCOUNT ALSO QUEUES THE CIC UPDATE (30 DAYS).
           MOVE 'KEEP' TO WS-STEP
           IF WS-MONTHS-UNUSED > 12
              IF WS-NOTICE-SENT = 'N'
                 MOVE 'NOTIFY' TO WS-STEP
              ELSE
                 IF WS-REPLY = 'N' AND WS-DAYS-SINCE-NOTICE > 30
                    AND WS-DUES = ZERO
                    MOVE 'CLOSE+CIC' TO WS-STEP
                 END-IF
              END-IF
           END-IF.
