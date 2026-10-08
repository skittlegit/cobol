       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTP20.
      * FIRM ONBOARDING - CALLS THE PARTNER RULE
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CAPITAL                PIC 9(3)V99 VALUE ZERO.
       01  WS-PROFIT                 PIC 9(3)V99 VALUE ZERO.
       01  WS-MGMT-CONTROL           PIC X(1) VALUE 'N'.
       01  WS-IS-BO                  PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CAPITAL
           ACCEPT WS-PROFIT
           ACCEPT WS-MGMT-CONTROL
           CALL 'QTP20K' USING WS-CAPITAL WS-PROFIT WS-MGMT-CONTROL
                               WS-IS-BO
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
