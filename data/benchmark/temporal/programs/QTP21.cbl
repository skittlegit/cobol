       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTP21.
      * PARTNERSHIP BO - ENTITLEMENT BANDS
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CAPITAL                PIC 9(3)V99 VALUE ZERO.
           88  CAPITAL-OWNER        VALUES 15.01 THRU 100.00.
       01  WS-PROFIT                 PIC 9(3)V99 VALUE ZERO.
           88  PROFIT-OWNER         VALUES 15.01 THRU 100.00.
       01  WS-MGMT-CONTROL           PIC X(1) VALUE 'N'.
       01  WS-IS-BO                  PIC X(1) VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CAPITAL
           ACCEPT WS-PROFIT
           ACCEPT WS-MGMT-CONTROL
           PERFORM 2000-PARTNER
           DISPLAY 'BO: ' WS-IS-BO
           STOP RUN.
       2000-PARTNER.
           IF CAPITAL-OWNER OR PROFIT-OWNER OR WS-MGMT-CONTROL = 'Y'
              MOVE 'Y' TO WS-IS-BO
           ELSE
              MOVE 'N' TO WS-IS-BO
           END-IF.
