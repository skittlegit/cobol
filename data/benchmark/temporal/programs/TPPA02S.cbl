       IDENTIFICATION DIVISION.
       PROGRAM-ID. TPPA02S.
      * PARTNER ENTITLEMENT SCREEN (CAPITAL OR PROFITS, OR CONTROL)
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PARTNER-LIMIT          PIC 9(3)V99 VALUE 15.00.
       LINKAGE SECTION.
       01  LK-PCT                    PIC 9(3)V99.
       01  LK-CTRL                   PIC X.
       01  LK-FLAG                   PIC X.
       PROCEDURE DIVISION USING LK-PCT LK-CTRL LK-FLAG.
       1000-SCREEN.
           IF LK-PCT > WS-PARTNER-LIMIT OR LK-CTRL = 'Y'
              MOVE 'Y' TO LK-FLAG
           ELSE
              MOVE 'N' TO LK-FLAG
           END-IF
           GOBACK.
