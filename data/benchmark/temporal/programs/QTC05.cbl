       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTC05.
      * COMPANY ONBOARDING - CALLS THE OWNERSHIP CHECK
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-OWNER-REC.
           05  WS-SHARES             PIC 9(3)V99.
           05  WS-CAPITAL            PIC 9(3)V99.
           05  WS-PROFITS            PIC 9(3)V99.
           05  WS-CONTROL            PIC X(1).
       01  WS-IS-BO                  PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-SHARES
           ACCEPT WS-CAPITAL
           ACCEPT WS-PROFITS
           ACCEPT WS-CONTROL
           CALL 'QTC05K' USING WS-OWNER-REC WS-IS-BO
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
