       IDENTIFICATION DIVISION.
       PROGRAM-ID. FALLTHRU.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY 'MAIN'.
      * MAIN-PARA has no terminating transfer, so control falls through into
      * NEXT-PARA even though nothing PERFORMs or GO TOs it.
       NEXT-PARA.
           DISPLAY 'NEXT'.
           GOBACK.
