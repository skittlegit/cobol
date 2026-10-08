       IDENTIFICATION DIVISION.
       PROGRAM-ID. QTC05K.
      * OWNERSHIP CHECK MODULE (COMPANY CUSTOMERS)
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-COMPANY-LIMIT          PIC 9(3)V99 VALUE 25.00.
       LINKAGE SECTION.
       01  LK-OWNER-REC.
           05  LK-SHARES             PIC 9(3)V99.
           05  LK-CAPITAL            PIC 9(3)V99.
           05  LK-PROFITS            PIC 9(3)V99.
           05  LK-CONTROL            PIC X(1).
       01  LK-IS-BO                  PIC X(1).
       PROCEDURE DIVISION USING LK-OWNER-REC LK-IS-BO.
       1000-CHECK.
           IF LK-SHARES > WS-COMPANY-LIMIT
              OR LK-CAPITAL > WS-COMPANY-LIMIT
              OR LK-PROFITS > WS-COMPANY-LIMIT OR LK-CONTROL = 'Y'
              MOVE 'Y' TO LK-IS-BO
           ELSE
              MOVE 'N' TO LK-IS-BO
           END-IF
           GOBACK.
