      *----------------------------------------------------------------
      * PENALTY DAY-BASIS CONFIGURATON COPYBOOK (SHARED)
      * BASIS 'W' = WORKING DAYS   BASIS 'C' = CALENDAR DAYS
      *----------------------------------------------------------------
       01  WS-DAY-BASIS-CONFIG.
           05  WS-DAY-BASIS          PIC X(1) VALUE 'W'.
               88  BASIS-WORKING     VALUE 'W'.
               88  BASIS-CALENDAR    VALUE 'C'.
           05  WS-PEN-RATE-STD       PIC 9(3) VALUE 500.
