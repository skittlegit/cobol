       IDENTIFICATION DIVISION.
       PROGRAM-ID. KYCSYNC3.
      * CKYCR UPLOAD AGEING - DUE DATE = RECEIPT + 7
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RECEIPT-DAY            PIC 9(5) VALUE ZERO.
       01  WS-TODAY-DAY              PIC 9(5) VALUE ZERO.
       01  WS-DUE-DAY                PIC 9(5) VALUE ZERO.
       01  WS-STATUS                 PIC X(8) VALUE SPACES.
       01  WS-RPT-HEADING            PIC X(29)
           VALUE 'CKYCR UPLOAD CONTROL'.
       01  WS-PAGE-NBR               PIC 9(4) VALUE ZERO.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-RECEIPT-DAY
           ACCEPT WS-TODAY-DAY
           COMPUTE WS-DUE-DAY = WS-RECEIPT-DAY + 7
           PERFORM 2000-CHK
           DISPLAY 'STATUS: ' WS-STATUS
           STOP RUN.
       2000-CHK.
           IF WS-TODAY-DAY > WS-DUE-DAY
              MOVE 'OVERDUE' TO WS-STATUS
           ELSE
              MOVE 'OK' TO WS-STATUS
           END-IF.
