       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTP20K.
      * PARTNER ENTITLEMENT RULE
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PARTNER-PCT            PIC 9(3)V99 VALUE 15.00.
       LINKAGE SECTION.
       01  LK-CAPITAL                PIC 9(3)V99.
       01  LK-PROFIT                 PIC 9(3)V99.
       01  LK-CONTROL                PIC X(1).
       01  LK-IS-BO                  PIC X(1).
       PROCEDURE DIVISION USING LK-CAPITAL LK-PROFIT
           LK-CONTROL LK-IS-BO.
       1000-RULE.
           IF LK-CAPITAL > WS-PARTNER-PCT OR LK-PROFIT > WS-PARTNER-PCT
              OR LK-CONTROL = 'Y'
              MOVE 'Y' TO LK-IS-BO
           ELSE
              MOVE 'N' TO LK-IS-BO
           END-IF
           GOBACK.
