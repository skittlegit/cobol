       IDENTIFICATION DIVISION.
       PROGRAM-ID. T6V2P4D.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CAPITAL-PCT           PIC 9(3)V99 VALUE ZERO.
       01  WS-PROFIT-PCT            PIC 9(3)V99 VALUE ZERO.
       01  WS-IS-BO                 PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-CAPITAL-PCT
           ACCEPT WS-PROFIT-PCT
           CALL 'T6V2BOSV' USING WS-CAPITAL-PCT
                                 WS-PROFIT-PCT
                                 WS-IS-BO
           DISPLAY WS-IS-BO
           STOP RUN.
       END PROGRAM T6V2P4D.

       IDENTIFICATION DIVISION.
       PROGRAM-ID. T6V2BOSV.
       DATA DIVISION.
       LINKAGE SECTION.
       01  LK-CAPITAL-PCT           PIC 9(3)V99.
       01  LK-PROFIT-PCT            PIC 9(3)V99.
       01  LK-IS-BO                 PIC X.
       PROCEDURE DIVISION USING LK-CAPITAL-PCT LK-PROFIT-PCT LK-IS-BO.
       2000-IDENTIFY-OWNER.
           IF LK-CAPITAL-PCT > 15 OR LK-PROFIT-PCT > 15
              MOVE 'Y' TO LK-IS-BO
           ELSE
              MOVE 'N' TO LK-IS-BO
           END-IF
           GOBACK.
       END PROGRAM T6V2BOSV.
