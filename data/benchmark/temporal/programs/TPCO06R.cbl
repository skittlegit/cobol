       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPCO06R.
      * OWNERSHIP RULE MODULE - CONTROLLING INTEREST TEST
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RULE-PCT               PIC 9(3)V99 VALUE 25.00.
       LINKAGE SECTION.
       01  LK-SHARE-PCT              PIC 9(3)V99.
       01  LK-CAPITAL-PCT            PIC 9(3)V99.
       01  LK-PROFIT-PCT             PIC 9(3)V99.
       01  LK-OTHER-CONTROL          PIC X.
       01  LK-IS-BO                  PIC X.
       PROCEDURE DIVISION USING LK-SHARE-PCT LK-CAPITAL-PCT
           LK-PROFIT-PCT LK-OTHER-CONTROL LK-IS-BO.
       1000-RULE.
           IF LK-SHARE-PCT > WS-RULE-PCT
              OR LK-CAPITAL-PCT > WS-RULE-PCT
              OR LK-PROFIT-PCT > WS-RULE-PCT
              OR LK-OTHER-CONTROL = 'Y'
              MOVE 'Y' TO LK-IS-BO
           ELSE
              MOVE 'N' TO LK-IS-BO
           END-IF
           GOBACK.
