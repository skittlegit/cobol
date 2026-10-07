       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPCO10S.
      * GENERIC STAKE SCREEN - LIMIT SUPPLIED BY THE CALLER
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CALLS                  PIC 9(5) VALUE ZERO.
       LINKAGE SECTION.
       01  LK-STAKE-PCT              PIC 9(3)V99.
       01  LK-LIMIT                  PIC 9(3)V99.
       01  LK-OTHER-CONTROL          PIC X.
       01  LK-IS-BO                  PIC X.
       PROCEDURE DIVISION USING LK-STAKE-PCT LK-LIMIT
           LK-OTHER-CONTROL LK-IS-BO.
       1000-SCREEN.
           ADD 1 TO WS-CALLS
           IF LK-STAKE-PCT > LK-LIMIT OR LK-OTHER-CONTROL = 'Y'
              MOVE 'Y' TO LK-IS-BO
           ELSE
              MOVE 'N' TO LK-IS-BO
           END-IF
           GOBACK.
