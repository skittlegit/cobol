       IDENTIFICATION DIVISION.
       PROGRAM-ID. GRVAGE1.
      *----------------------------------------------------------------
      * GRIEVANCE AGEING - ESCALATE IF NO RESPONSE WITHIN ONE MONTH
      * OF COMPLAINT LODGEMENT (OMBUDSMAN ELIGIBILITY MARKER)
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-COMPLAINT-DATE.
           05  WS-CMP-YYYY           PIC 9(4) VALUE ZERO.
           05  WS-CMP-MM             PIC 9(2) VALUE ZERO.
           05  WS-CMP-DD             PIC 9(2) VALUE ZERO.
       01  WS-CHECK-DATE.
           05  WS-CHK-YYYY           PIC 9(4) VALUE ZERO.
           05  WS-CHK-MM             PIC 9(2) VALUE ZERO.
           05  WS-CHK-DD             PIC 9(2) VALUE ZERO.
       01  WS-DUE-DATE.
           05  WS-DUE-YYYY           PIC 9(4) VALUE ZERO.
           05  WS-DUE-MM             PIC 9(2) VALUE ZERO.
           05  WS-DUE-DD             PIC 9(2) VALUE ZERO.
       01  WS-FLAGS.
           05  WS-ESCALATE           PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-COMPLAINT-DATE
           ACCEPT WS-CHECK-DATE
           PERFORM 2000-DUE-DATE
           PERFORM 3000-COMPARE
           DISPLAY 'ESCALATE: ' WS-ESCALATE
           STOP RUN.
       2000-DUE-DATE.
           MOVE WS-CMP-DD TO WS-DUE-DD
           IF WS-CMP-MM = 12
              MOVE 01 TO WS-DUE-MM
              COMPUTE WS-DUE-YYYY = WS-CMP-YYYY + 1
           ELSE
              COMPUTE WS-DUE-MM = WS-CMP-MM + 1
              MOVE WS-CMP-YYYY TO WS-DUE-YYYY
           END-IF.
       3000-COMPARE.
           IF WS-CHECK-DATE > WS-DUE-DATE
              MOVE 'Y' TO WS-ESCALATE
           END-IF.
