       IDENTIFICATION DIVISION.
       PROGRAM-ID. SCRNGATE1.
      *----------------------------------------------------------------
      * UNSC SANCTIONS SCREENING GATE - THE APPLICANT LIST-SOURCE IS
      * SCREENED AGAINST THE MANDATED SANCTIONS REGISTRY; A MATCH
      * BLOCKS ONBOARDING.
      *----------------------------------------------------------------
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY SANCREG.
       01  WS-SCREEN-RESULT PIC X(5) VALUE 'CLEAR'.
       PROCEDURE DIVISION.
       1000-MAIN.
           ACCEPT WS-LIST-SOURCE
           PERFORM 2000-SCREEN-SANCTIONS
           DISPLAY 'SCREEN: ' WS-SCREEN-RESULT
           STOP RUN.
       2000-SCREEN-SANCTIONS.
           IF MANDATED-LIST
              MOVE 'BLOCK' TO WS-SCREEN-RESULT
           ELSE
              MOVE 'CLEAR' TO WS-SCREEN-RESULT
           END-IF.
