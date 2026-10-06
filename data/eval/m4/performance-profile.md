# T8.4 performance profile

## Measurement scope

Evidence: `performance-profile.json:/measurement_scope`

```json
"Canonical host trajectory observations; no provider-resource estimates"
```

## Host observations by system and cell

Evidence: `performance-profile.json:/systems`

```json
{
  "adaptive_agent": {
    "D1_stale_threshold": {
      "answered": 43,
      "error_observations": 6,
      "host_observation_latency_ms": {
        "maximum": 172.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 403,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 334
      },
      "host_per_tool_latency_ms": {
        "get_data_layout": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 3,
          "zero_values": 2
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 82,
          "zero_values": 80
        },
        "read_paragraph": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 133,
          "zero_values": 113
        },
        "read_program": {
          "maximum": 172.0,
          "median": 0.0,
          "samples": 71,
          "zero_values": 52
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 17,
          "zero_values": 17
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 57,
          "zero_values": 44
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 40,
          "zero_values": 26
        }
      },
      "repeated_tool_arguments": 41,
      "rows": 61,
      "successful_observations": 397,
      "tool_calls": 403,
      "tools": {
        "get_data_layout": 3,
        "grep": 82,
        "read_paragraph": 133,
        "read_program": 71,
        "resolve_copybook": 17,
        "slice_on": 57,
        "trace_variable": 40
      }
    },
    "D1_stale_threshold/interprocedural": {
      "answered": 6,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 32.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 128,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 99
      },
      "host_per_tool_latency_ms": {
        "get_data_layout": {
          "maximum": 16.0,
          "median": 16.0,
          "samples": 1,
          "zero_values": 0
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 31,
          "zero_values": 29
        },
        "read_paragraph": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 33,
          "zero_values": 25
        },
        "read_program": {
          "maximum": 31.0,
          "median": 15.0,
          "samples": 14,
          "zero_values": 6
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 16,
          "zero_values": 16
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 16
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 9,
          "zero_values": 7
        }
      },
      "repeated_tool_arguments": 25,
      "rows": 12,
      "successful_observations": 128,
      "tool_calls": 128,
      "tools": {
        "get_data_layout": 1,
        "grep": 31,
        "read_paragraph": 33,
        "read_program": 14,
        "resolve_copybook": 16,
        "slice_on": 24,
        "trace_variable": 9
      }
    },
    "D1_stale_threshold/local": {
      "answered": 37,
      "error_observations": 6,
      "host_observation_latency_ms": {
        "maximum": 172.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 275,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 235
      },
      "host_per_tool_latency_ms": {
        "get_data_layout": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "grep": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 51,
          "zero_values": 51
        },
        "read_paragraph": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 100,
          "zero_values": 88
        },
        "read_program": {
          "maximum": 172.0,
          "median": 0.0,
          "samples": 57,
          "zero_values": 46
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 1,
          "zero_values": 1
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 33,
          "zero_values": 28
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 31,
          "zero_values": 19
        }
      },
      "repeated_tool_arguments": 16,
      "rows": 49,
      "successful_observations": 269,
      "tool_calls": 275,
      "tools": {
        "get_data_layout": 2,
        "grep": 51,
        "read_paragraph": 100,
        "read_program": 57,
        "resolve_copybook": 1,
        "slice_on": 33,
        "trace_variable": 31
      }
    },
    "D2_missing_rule": {
      "answered": 11,
      "error_observations": 2,
      "host_observation_latency_ms": {
        "maximum": 62.0,
        "median": 0.0,
        "p95_nearest_rank": 31.0,
        "samples": 98,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 63
      },
      "host_per_tool_latency_ms": {
        "get_data_layout": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 4,
          "zero_values": 3
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 28,
          "zero_values": 24
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 30,
          "zero_values": 16
        },
        "read_program": {
          "maximum": 62.0,
          "median": 0.0,
          "samples": 14,
          "zero_values": 10
        },
        "slice_on": {
          "maximum": 31.0,
          "median": 15.0,
          "samples": 20,
          "zero_values": 9
        },
        "trace_variable": {
          "maximum": 31.0,
          "median": 15.5,
          "samples": 2,
          "zero_values": 1
        }
      },
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 96,
      "tool_calls": 98,
      "tools": {
        "get_data_layout": 4,
        "grep": 28,
        "read_paragraph": 30,
        "read_program": 14,
        "slice_on": 20,
        "trace_variable": 2
      }
    },
    "D2_missing_rule/local": {
      "answered": 11,
      "error_observations": 2,
      "host_observation_latency_ms": {
        "maximum": 62.0,
        "median": 0.0,
        "p95_nearest_rank": 31.0,
        "samples": 98,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 63
      },
      "host_per_tool_latency_ms": {
        "get_data_layout": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 4,
          "zero_values": 3
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 28,
          "zero_values": 24
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 30,
          "zero_values": 16
        },
        "read_program": {
          "maximum": 62.0,
          "median": 0.0,
          "samples": 14,
          "zero_values": 10
        },
        "slice_on": {
          "maximum": 31.0,
          "median": 15.0,
          "samples": 20,
          "zero_values": 9
        },
        "trace_variable": {
          "maximum": 31.0,
          "median": 15.5,
          "samples": 2,
          "zero_values": 1
        }
      },
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 96,
      "tool_calls": 98,
      "tools": {
        "get_data_layout": 4,
        "grep": 28,
        "read_paragraph": 30,
        "read_program": 14,
        "slice_on": 20,
        "trace_variable": 2
      }
    },
    "D3_contradictory": {
      "answered": 17,
      "error_observations": 8,
      "host_observation_latency_ms": {
        "maximum": 16.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 169,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 144
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "find_callers": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 51,
          "zero_values": 50
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 52,
          "zero_values": 47
        },
        "read_program": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 26,
          "zero_values": 19
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 22,
          "zero_values": 15
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 14,
          "zero_values": 9
        }
      },
      "repeated_tool_arguments": 20,
      "rows": 23,
      "successful_observations": 161,
      "tool_calls": 169,
      "tools": {
        "find_callees": 2,
        "find_callers": 2,
        "grep": 51,
        "read_paragraph": 52,
        "read_program": 26,
        "slice_on": 22,
        "trace_variable": 14
      }
    },
    "D3_contradictory/interprocedural": {
      "answered": 6,
      "error_observations": 8,
      "host_observation_latency_ms": {
        "maximum": 16.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 91,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 79
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "find_callers": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 39,
          "zero_values": 38
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 20,
          "zero_values": 19
        },
        "read_program": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 9,
          "zero_values": 7
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 12,
          "zero_values": 8
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 15.0,
          "samples": 7,
          "zero_values": 3
        }
      },
      "repeated_tool_arguments": 14,
      "rows": 8,
      "successful_observations": 83,
      "tool_calls": 91,
      "tools": {
        "find_callees": 2,
        "find_callers": 2,
        "grep": 39,
        "read_paragraph": 20,
        "read_program": 9,
        "slice_on": 12,
        "trace_variable": 7
      }
    },
    "D3_contradictory/local": {
      "answered": 11,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 16.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 78,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 65
      },
      "host_per_tool_latency_ms": {
        "grep": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 12,
          "zero_values": 12
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 32,
          "zero_values": 28
        },
        "read_program": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 17,
          "zero_values": 12
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 10,
          "zero_values": 7
        },
        "trace_variable": {
          "maximum": 15.0,
          "median": 0.0,
          "samples": 7,
          "zero_values": 6
        }
      },
      "repeated_tool_arguments": 6,
      "rows": 15,
      "successful_observations": 78,
      "tool_calls": 78,
      "tools": {
        "grep": 12,
        "read_paragraph": 32,
        "read_program": 17,
        "slice_on": 10,
        "trace_variable": 7
      }
    },
    "D4_stale_reference_data": {
      "answered": 12,
      "error_observations": 2,
      "host_observation_latency_ms": {
        "maximum": 31.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 128,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 109
      },
      "host_per_tool_latency_ms": {
        "get_data_layout": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 10,
          "zero_values": 7
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 30,
          "zero_values": 26
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 35,
          "zero_values": 28
        },
        "read_program": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 16,
          "zero_values": 13
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 18,
          "zero_values": 18
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 12,
          "zero_values": 10
        },
        "trace_variable": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 7,
          "zero_values": 7
        }
      },
      "repeated_tool_arguments": 19,
      "rows": 14,
      "successful_observations": 126,
      "tool_calls": 128,
      "tools": {
        "get_data_layout": 10,
        "grep": 30,
        "read_paragraph": 35,
        "read_program": 16,
        "resolve_copybook": 18,
        "slice_on": 12,
        "trace_variable": 7
      }
    },
    "D4_stale_reference_data/local": {
      "answered": 12,
      "error_observations": 2,
      "host_observation_latency_ms": {
        "maximum": 31.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 128,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 109
      },
      "host_per_tool_latency_ms": {
        "get_data_layout": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 10,
          "zero_values": 7
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 30,
          "zero_values": 26
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 35,
          "zero_values": 28
        },
        "read_program": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 16,
          "zero_values": 13
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 18,
          "zero_values": 18
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 12,
          "zero_values": 10
        },
        "trace_variable": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 7,
          "zero_values": 7
        }
      },
      "repeated_tool_arguments": 19,
      "rows": 14,
      "successful_observations": 126,
      "tool_calls": 128,
      "tools": {
        "get_data_layout": 10,
        "grep": 30,
        "read_paragraph": 35,
        "read_program": 16,
        "resolve_copybook": 18,
        "slice_on": 12,
        "trace_variable": 7
      }
    },
    "D5_boundary_error": {
      "answered": 16,
      "error_observations": 19,
      "host_observation_latency_ms": {
        "maximum": 2375.0,
        "median": 0.0,
        "p95_nearest_rank": 1813.0,
        "samples": 133,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 101
      },
      "host_per_tool_latency_ms": {
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 12
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 40,
          "zero_values": 35
        },
        "read_program": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 19,
          "zero_values": 15
        },
        "run_cobol": {
          "maximum": 2375.0,
          "median": 0.0,
          "samples": 30,
          "zero_values": 17
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 11,
          "zero_values": 7
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 20,
          "zero_values": 15
        }
      },
      "repeated_tool_arguments": 11,
      "rows": 18,
      "successful_observations": 114,
      "tool_calls": 133,
      "tools": {
        "grep": 13,
        "read_paragraph": 40,
        "read_program": 19,
        "run_cobol": 30,
        "slice_on": 11,
        "trace_variable": 20
      }
    },
    "D5_boundary_error/local": {
      "answered": 16,
      "error_observations": 19,
      "host_observation_latency_ms": {
        "maximum": 2375.0,
        "median": 0.0,
        "p95_nearest_rank": 1813.0,
        "samples": 133,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 101
      },
      "host_per_tool_latency_ms": {
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 12
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 40,
          "zero_values": 35
        },
        "read_program": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 19,
          "zero_values": 15
        },
        "run_cobol": {
          "maximum": 2375.0,
          "median": 0.0,
          "samples": 30,
          "zero_values": 17
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 11,
          "zero_values": 7
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 20,
          "zero_values": 15
        }
      },
      "repeated_tool_arguments": 11,
      "rows": 18,
      "successful_observations": 114,
      "tool_calls": 133,
      "tools": {
        "grep": 13,
        "read_paragraph": 40,
        "read_program": 19,
        "run_cobol": 30,
        "slice_on": 11,
        "trace_variable": 20
      }
    },
    "D6_dead_code": {
      "answered": 9,
      "error_observations": 2,
      "host_observation_latency_ms": {
        "maximum": 1844.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 180,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 146
      },
      "host_per_tool_latency_ms": {
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 69,
          "zero_values": 64
        },
        "read_paragraph": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 45,
          "zero_values": 34
        },
        "read_program": {
          "maximum": 1844.0,
          "median": 0.0,
          "samples": 23,
          "zero_values": 17
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 4,
          "zero_values": 4
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 18,
          "zero_values": 14
        },
        "trace_variable": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 21,
          "zero_values": 13
        }
      },
      "repeated_tool_arguments": 4,
      "rows": 23,
      "successful_observations": 178,
      "tool_calls": 180,
      "tools": {
        "grep": 69,
        "read_paragraph": 45,
        "read_program": 23,
        "resolve_copybook": 4,
        "slice_on": 18,
        "trace_variable": 21
      }
    },
    "D6_dead_code/interprocedural": {
      "answered": 9,
      "error_observations": 1,
      "host_observation_latency_ms": {
        "maximum": 1844.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 110,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 88
      },
      "host_per_tool_latency_ms": {
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 45,
          "zero_values": 41
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 26,
          "zero_values": 19
        },
        "read_program": {
          "maximum": 1844.0,
          "median": 0.0,
          "samples": 12,
          "zero_values": 9
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 4,
          "zero_values": 4
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 14,
          "zero_values": 10
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 9,
          "zero_values": 5
        }
      },
      "repeated_tool_arguments": 4,
      "rows": 12,
      "successful_observations": 109,
      "tool_calls": 110,
      "tools": {
        "grep": 45,
        "read_paragraph": 26,
        "read_program": 12,
        "resolve_copybook": 4,
        "slice_on": 14,
        "trace_variable": 9
      }
    },
    "D6_dead_code/local": {
      "answered": 0,
      "error_observations": 1,
      "host_observation_latency_ms": {
        "maximum": 63.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 70,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 58
      },
      "host_per_tool_latency_ms": {
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 23
        },
        "read_paragraph": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 19,
          "zero_values": 15
        },
        "read_program": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 11,
          "zero_values": 8
        },
        "slice_on": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 4,
          "zero_values": 4
        },
        "trace_variable": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 12,
          "zero_values": 8
        }
      },
      "repeated_tool_arguments": 0,
      "rows": 11,
      "successful_observations": 69,
      "tool_calls": 70,
      "tools": {
        "grep": 24,
        "read_paragraph": 19,
        "read_program": 11,
        "slice_on": 4,
        "trace_variable": 12
      }
    },
    "D7_conformant": {
      "answered": 31,
      "error_observations": 7,
      "host_observation_latency_ms": {
        "maximum": 75781.0,
        "median": 0.0,
        "p95_nearest_rank": 31.0,
        "samples": 301,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 225
      },
      "host_per_tool_latency_ms": {
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 65,
          "zero_values": 59
        },
        "read_paragraph": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 101,
          "zero_values": 65
        },
        "read_program": {
          "maximum": 62.0,
          "median": 0.0,
          "samples": 46,
          "zero_values": 37
        },
        "run_cobol": {
          "maximum": 2266.0,
          "median": 109.0,
          "samples": 8,
          "zero_values": 4
        },
        "search_regulations": {
          "maximum": 75781.0,
          "median": 75781.0,
          "samples": 1,
          "zero_values": 0
        },
        "slice_on": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 55,
          "zero_values": 38
        },
        "trace_variable": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 25,
          "zero_values": 22
        }
      },
      "repeated_tool_arguments": 12,
      "rows": 43,
      "successful_observations": 294,
      "tool_calls": 301,
      "tools": {
        "grep": 65,
        "read_paragraph": 101,
        "read_program": 46,
        "run_cobol": 8,
        "search_regulations": 1,
        "slice_on": 55,
        "trace_variable": 25
      }
    },
    "D7_conformant/interprocedural": {
      "answered": 1,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 63.0,
        "median": 15.0,
        "p95_nearest_rank": 62.0,
        "samples": 36,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 12
      },
      "host_per_tool_latency_ms": {
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 8,
          "zero_values": 5
        },
        "read_paragraph": {
          "maximum": 32.0,
          "median": 16.0,
          "samples": 17,
          "zero_values": 4
        },
        "read_program": {
          "maximum": 62.0,
          "median": 15.0,
          "samples": 5,
          "zero_values": 2
        },
        "slice_on": {
          "maximum": 63.0,
          "median": 31.0,
          "samples": 5,
          "zero_values": 1
        },
        "trace_variable": {
          "maximum": 47.0,
          "median": 47.0,
          "samples": 1,
          "zero_values": 0
        }
      },
      "repeated_tool_arguments": 0,
      "rows": 4,
      "successful_observations": 36,
      "tool_calls": 36,
      "tools": {
        "grep": 8,
        "read_paragraph": 17,
        "read_program": 5,
        "slice_on": 5,
        "trace_variable": 1
      }
    },
    "D7_conformant/local": {
      "answered": 30,
      "error_observations": 7,
      "host_observation_latency_ms": {
        "maximum": 75781.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 265,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 213
      },
      "host_per_tool_latency_ms": {
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 57,
          "zero_values": 54
        },
        "read_paragraph": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 84,
          "zero_values": 61
        },
        "read_program": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 41,
          "zero_values": 35
        },
        "run_cobol": {
          "maximum": 2266.0,
          "median": 109.0,
          "samples": 8,
          "zero_values": 4
        },
        "search_regulations": {
          "maximum": 75781.0,
          "median": 75781.0,
          "samples": 1,
          "zero_values": 0
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 50,
          "zero_values": 37
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 22
        }
      },
      "repeated_tool_arguments": 12,
      "rows": 39,
      "successful_observations": 258,
      "tool_calls": 265,
      "tools": {
        "grep": 57,
        "read_paragraph": 84,
        "read_program": 41,
        "run_cobol": 8,
        "search_regulations": 1,
        "slice_on": 50,
        "trace_variable": 24
      }
    },
    "interprocedural": {
      "answered": 22,
      "error_observations": 9,
      "host_observation_latency_ms": {
        "maximum": 1844.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 365,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 278
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "find_callers": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "get_data_layout": {
          "maximum": 16.0,
          "median": 16.0,
          "samples": 1,
          "zero_values": 0
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 123,
          "zero_values": 113
        },
        "read_paragraph": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 96,
          "zero_values": 67
        },
        "read_program": {
          "maximum": 1844.0,
          "median": 0.0,
          "samples": 40,
          "zero_values": 24
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 20,
          "zero_values": 20
        },
        "slice_on": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 55,
          "zero_values": 35
        },
        "trace_variable": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 26,
          "zero_values": 15
        }
      },
      "repeated_tool_arguments": 43,
      "rows": 36,
      "successful_observations": 356,
      "tool_calls": 365,
      "tools": {
        "find_callees": 2,
        "find_callers": 2,
        "get_data_layout": 1,
        "grep": 123,
        "read_paragraph": 96,
        "read_program": 40,
        "resolve_copybook": 20,
        "slice_on": 55,
        "trace_variable": 26
      }
    },
    "local": {
      "answered": 117,
      "error_observations": 37,
      "host_observation_latency_ms": {
        "maximum": 75781.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 1047,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 844
      },
      "host_per_tool_latency_ms": {
        "get_data_layout": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 16,
          "zero_values": 12
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 215,
          "zero_values": 202
        },
        "read_paragraph": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 340,
          "zero_values": 271
        },
        "read_program": {
          "maximum": 172.0,
          "median": 0.0,
          "samples": 175,
          "zero_values": 139
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 19,
          "zero_values": 19
        },
        "run_cobol": {
          "maximum": 2375.0,
          "median": 0.0,
          "samples": 38,
          "zero_values": 21
        },
        "search_regulations": {
          "maximum": 75781.0,
          "median": 75781.0,
          "samples": 1,
          "zero_values": 0
        },
        "slice_on": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 140,
          "zero_values": 102
        },
        "trace_variable": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 103,
          "zero_values": 78
        }
      },
      "repeated_tool_arguments": 64,
      "rows": 160,
      "successful_observations": 1010,
      "tool_calls": 1047,
      "tools": {
        "get_data_layout": 16,
        "grep": 215,
        "read_paragraph": 340,
        "read_program": 175,
        "resolve_copybook": 19,
        "run_cobol": 38,
        "search_regulations": 1,
        "slice_on": 140,
        "trace_variable": 103
      }
    },
    "overall": {
      "answered": 139,
      "error_observations": 46,
      "host_observation_latency_ms": {
        "maximum": 75781.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 1412,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 1122
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "find_callers": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "get_data_layout": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 17,
          "zero_values": 12
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 338,
          "zero_values": 315
        },
        "read_paragraph": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 436,
          "zero_values": 338
        },
        "read_program": {
          "maximum": 1844.0,
          "median": 0.0,
          "samples": 215,
          "zero_values": 163
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 39,
          "zero_values": 39
        },
        "run_cobol": {
          "maximum": 2375.0,
          "median": 0.0,
          "samples": 38,
          "zero_values": 21
        },
        "search_regulations": {
          "maximum": 75781.0,
          "median": 75781.0,
          "samples": 1,
          "zero_values": 0
        },
        "slice_on": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 195,
          "zero_values": 137
        },
        "trace_variable": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 129,
          "zero_values": 93
        }
      },
      "repeated_tool_arguments": 107,
      "rows": 196,
      "successful_observations": 1366,
      "tool_calls": 1412,
      "tools": {
        "find_callees": 2,
        "find_callers": 2,
        "get_data_layout": 17,
        "grep": 338,
        "read_paragraph": 436,
        "read_program": 215,
        "resolve_copybook": 39,
        "run_cobol": 38,
        "search_regulations": 1,
        "slice_on": 195,
        "trace_variable": 129
      }
    }
  },
  "agent": {
    "D1_stale_threshold": {
      "answered": 50,
      "error_observations": 1,
      "host_observation_latency_ms": {
        "maximum": 62.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 1266,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 1069
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 62,
          "zero_values": 46
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 108,
          "zero_values": 88
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 227,
          "zero_values": 216
        },
        "read_paragraph": {
          "maximum": 62.0,
          "median": 0.0,
          "samples": 416,
          "zero_values": 346
        },
        "read_program": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 277,
          "zero_values": 230
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 35,
          "zero_values": 35
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 107,
          "zero_values": 84
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 34,
          "zero_values": 24
        }
      },
      "repeated_tool_arguments": 695,
      "rows": 61,
      "successful_observations": 1265,
      "tool_calls": 1266,
      "tools": {
        "find_callees": 62,
        "find_callers": 108,
        "grep": 227,
        "read_paragraph": 416,
        "read_program": 277,
        "resolve_copybook": 35,
        "slice_on": 107,
        "trace_variable": 34
      }
    },
    "D1_stale_threshold/interprocedural": {
      "answered": 8,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 16.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 283,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 246
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 8
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 18
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 61,
          "zero_values": 54
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 78,
          "zero_values": 71
        },
        "read_program": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 52,
          "zero_values": 43
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 33,
          "zero_values": 33
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 21,
          "zero_values": 18
        },
        "trace_variable": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 1,
          "zero_values": 1
        }
      },
      "repeated_tool_arguments": 129,
      "rows": 12,
      "successful_observations": 283,
      "tool_calls": 283,
      "tools": {
        "find_callees": 13,
        "find_callers": 24,
        "grep": 61,
        "read_paragraph": 78,
        "read_program": 52,
        "resolve_copybook": 33,
        "slice_on": 21,
        "trace_variable": 1
      }
    },
    "D1_stale_threshold/local": {
      "answered": 42,
      "error_observations": 1,
      "host_observation_latency_ms": {
        "maximum": 62.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 983,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 823
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 49,
          "zero_values": 38
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 84,
          "zero_values": 70
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 166,
          "zero_values": 162
        },
        "read_paragraph": {
          "maximum": 62.0,
          "median": 0.0,
          "samples": 338,
          "zero_values": 275
        },
        "read_program": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 225,
          "zero_values": 187
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 2,
          "zero_values": 2
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 86,
          "zero_values": 66
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 33,
          "zero_values": 23
        }
      },
      "repeated_tool_arguments": 566,
      "rows": 49,
      "successful_observations": 982,
      "tool_calls": 983,
      "tools": {
        "find_callees": 49,
        "find_callers": 84,
        "grep": 166,
        "read_paragraph": 338,
        "read_program": 225,
        "resolve_copybook": 2,
        "slice_on": 86,
        "trace_variable": 33
      }
    },
    "D2_missing_rule": {
      "answered": 2,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 32.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 288,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 229
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 16,
          "zero_values": 13
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 20
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 49,
          "zero_values": 48
        },
        "read_paragraph": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 107,
          "zero_values": 82
        },
        "read_program": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 65,
          "zero_values": 52
        },
        "slice_on": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 19,
          "zero_values": 10
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 7.5,
          "samples": 8,
          "zero_values": 4
        }
      },
      "repeated_tool_arguments": 158,
      "rows": 14,
      "successful_observations": 288,
      "tool_calls": 288,
      "tools": {
        "find_callees": 16,
        "find_callers": 24,
        "grep": 49,
        "read_paragraph": 107,
        "read_program": 65,
        "slice_on": 19,
        "trace_variable": 8
      }
    },
    "D2_missing_rule/local": {
      "answered": 2,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 32.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 288,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 229
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 16,
          "zero_values": 13
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 20
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 49,
          "zero_values": 48
        },
        "read_paragraph": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 107,
          "zero_values": 82
        },
        "read_program": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 65,
          "zero_values": 52
        },
        "slice_on": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 19,
          "zero_values": 10
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 7.5,
          "samples": 8,
          "zero_values": 4
        }
      },
      "repeated_tool_arguments": 158,
      "rows": 14,
      "successful_observations": 288,
      "tool_calls": 288,
      "tools": {
        "find_callees": 16,
        "find_callers": 24,
        "grep": 49,
        "read_paragraph": 107,
        "read_program": 65,
        "slice_on": 19,
        "trace_variable": 8
      }
    },
    "D3_contradictory": {
      "answered": 16,
      "error_observations": 12,
      "host_observation_latency_ms": {
        "maximum": 203.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 432,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 372
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 21
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 35,
          "zero_values": 29
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 90,
          "zero_values": 86
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 142,
          "zero_values": 117
        },
        "read_program": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 90,
          "zero_values": 78
        },
        "run_cobol": {
          "maximum": 203.0,
          "median": 188.0,
          "samples": 3,
          "zero_values": 1
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 33,
          "zero_values": 26
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 15,
          "zero_values": 14
        }
      },
      "repeated_tool_arguments": 212,
      "rows": 23,
      "successful_observations": 420,
      "tool_calls": 432,
      "tools": {
        "find_callees": 24,
        "find_callers": 35,
        "grep": 90,
        "read_paragraph": 142,
        "read_program": 90,
        "run_cobol": 3,
        "slice_on": 33,
        "trace_variable": 15
      }
    },
    "D3_contradictory/interprocedural": {
      "answered": 2,
      "error_observations": 11,
      "host_observation_latency_ms": {
        "maximum": 203.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 158,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 141
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 9,
          "zero_values": 8
        },
        "find_callers": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 9,
          "zero_values": 9
        },
        "grep": {
          "maximum": 15.0,
          "median": 0.0,
          "samples": 34,
          "zero_values": 33
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 50,
          "zero_values": 43
        },
        "read_program": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 29,
          "zero_values": 26
        },
        "run_cobol": {
          "maximum": 203.0,
          "median": 188.0,
          "samples": 3,
          "zero_values": 1
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 11
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 11,
          "zero_values": 10
        }
      },
      "repeated_tool_arguments": 69,
      "rows": 8,
      "successful_observations": 147,
      "tool_calls": 158,
      "tools": {
        "find_callees": 9,
        "find_callers": 9,
        "grep": 34,
        "read_paragraph": 50,
        "read_program": 29,
        "run_cobol": 3,
        "slice_on": 13,
        "trace_variable": 11
      }
    },
    "D3_contradictory/local": {
      "answered": 14,
      "error_observations": 1,
      "host_observation_latency_ms": {
        "maximum": 31.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 274,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 231
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 15,
          "zero_values": 13
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 26,
          "zero_values": 20
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 56,
          "zero_values": 53
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 92,
          "zero_values": 74
        },
        "read_program": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 61,
          "zero_values": 52
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 20,
          "zero_values": 15
        },
        "trace_variable": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 4,
          "zero_values": 4
        }
      },
      "repeated_tool_arguments": 143,
      "rows": 15,
      "successful_observations": 273,
      "tool_calls": 274,
      "tools": {
        "find_callees": 15,
        "find_callers": 26,
        "grep": 56,
        "read_paragraph": 92,
        "read_program": 61,
        "slice_on": 20,
        "trace_variable": 4
      }
    },
    "D4_stale_reference_data": {
      "answered": 8,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 32.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 304,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 259
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 12
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 20
        },
        "get_data_layout": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 3,
          "zero_values": 3
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 65,
          "zero_values": 58
        },
        "read_paragraph": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 88,
          "zero_values": 73
        },
        "read_program": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 57,
          "zero_values": 46
        },
        "resolve_copybook": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 36,
          "zero_values": 33
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 16,
          "zero_values": 13
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 8.0,
          "samples": 2,
          "zero_values": 1
        }
      },
      "repeated_tool_arguments": 147,
      "rows": 14,
      "successful_observations": 304,
      "tool_calls": 304,
      "tools": {
        "find_callees": 13,
        "find_callers": 24,
        "get_data_layout": 3,
        "grep": 65,
        "read_paragraph": 88,
        "read_program": 57,
        "resolve_copybook": 36,
        "slice_on": 16,
        "trace_variable": 2
      }
    },
    "D4_stale_reference_data/local": {
      "answered": 8,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 32.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 304,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 259
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 12
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 20
        },
        "get_data_layout": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 3,
          "zero_values": 3
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 65,
          "zero_values": 58
        },
        "read_paragraph": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 88,
          "zero_values": 73
        },
        "read_program": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 57,
          "zero_values": 46
        },
        "resolve_copybook": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 36,
          "zero_values": 33
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 16,
          "zero_values": 13
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 8.0,
          "samples": 2,
          "zero_values": 1
        }
      },
      "repeated_tool_arguments": 147,
      "rows": 14,
      "successful_observations": 304,
      "tool_calls": 304,
      "tools": {
        "find_callees": 13,
        "find_callers": 24,
        "get_data_layout": 3,
        "grep": 65,
        "read_paragraph": 88,
        "read_program": 57,
        "resolve_copybook": 36,
        "slice_on": 16,
        "trace_variable": 2
      }
    },
    "D5_boundary_error": {
      "answered": 11,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 1125.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 352,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 289
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 18,
          "zero_values": 15
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 31,
          "zero_values": 25
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 77,
          "zero_values": 73
        },
        "read_paragraph": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 112,
          "zero_values": 86
        },
        "read_program": {
          "maximum": 1125.0,
          "median": 0.0,
          "samples": 77,
          "zero_values": 65
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 29,
          "zero_values": 20
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 8,
          "zero_values": 5
        }
      },
      "repeated_tool_arguments": 180,
      "rows": 18,
      "successful_observations": 352,
      "tool_calls": 352,
      "tools": {
        "find_callees": 18,
        "find_callers": 31,
        "grep": 77,
        "read_paragraph": 112,
        "read_program": 77,
        "slice_on": 29,
        "trace_variable": 8
      }
    },
    "D5_boundary_error/local": {
      "answered": 11,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 1125.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 352,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 289
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 18,
          "zero_values": 15
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 31,
          "zero_values": 25
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 77,
          "zero_values": 73
        },
        "read_paragraph": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 112,
          "zero_values": 86
        },
        "read_program": {
          "maximum": 1125.0,
          "median": 0.0,
          "samples": 77,
          "zero_values": 65
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 29,
          "zero_values": 20
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 8,
          "zero_values": 5
        }
      },
      "repeated_tool_arguments": 180,
      "rows": 18,
      "successful_observations": 352,
      "tool_calls": 352,
      "tools": {
        "find_callees": 18,
        "find_callers": 31,
        "grep": 77,
        "read_paragraph": 112,
        "read_program": 77,
        "slice_on": 29,
        "trace_variable": 8
      }
    },
    "D6_dead_code": {
      "answered": 9,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 1813.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 482,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 414
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 24,
          "zero_values": 22
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 29,
          "zero_values": 26
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 87,
          "zero_values": 79
        },
        "read_paragraph": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 185,
          "zero_values": 155
        },
        "read_program": {
          "maximum": 1813.0,
          "median": 0.0,
          "samples": 97,
          "zero_values": 85
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 3,
          "zero_values": 3
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 44,
          "zero_values": 35
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 9
        }
      },
      "repeated_tool_arguments": 250,
      "rows": 23,
      "successful_observations": 482,
      "tool_calls": 482,
      "tools": {
        "find_callees": 24,
        "find_callers": 29,
        "grep": 87,
        "read_paragraph": 185,
        "read_program": 97,
        "resolve_copybook": 3,
        "slice_on": 44,
        "trace_variable": 13
      }
    },
    "D6_dead_code/interprocedural": {
      "answered": 2,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 31.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 217,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 188
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 11
        },
        "find_callers": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 18,
          "zero_values": 17
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 30,
          "zero_values": 24
        },
        "read_paragraph": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 93,
          "zero_values": 81
        },
        "read_program": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 47,
          "zero_values": 43
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 3,
          "zero_values": 3
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 9
        }
      },
      "repeated_tool_arguments": 116,
      "rows": 12,
      "successful_observations": 217,
      "tool_calls": 217,
      "tools": {
        "find_callees": 13,
        "find_callers": 18,
        "grep": 30,
        "read_paragraph": 93,
        "read_program": 47,
        "resolve_copybook": 3,
        "slice_on": 13
      }
    },
    "D6_dead_code/local": {
      "answered": 7,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 1813.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 265,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 226
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 11,
          "zero_values": 11
        },
        "find_callers": {
          "maximum": 15.0,
          "median": 0.0,
          "samples": 11,
          "zero_values": 9
        },
        "grep": {
          "maximum": 15.0,
          "median": 0.0,
          "samples": 57,
          "zero_values": 55
        },
        "read_paragraph": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 92,
          "zero_values": 74
        },
        "read_program": {
          "maximum": 1813.0,
          "median": 0.0,
          "samples": 50,
          "zero_values": 42
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 31,
          "zero_values": 26
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 9
        }
      },
      "repeated_tool_arguments": 134,
      "rows": 11,
      "successful_observations": 265,
      "tool_calls": 265,
      "tools": {
        "find_callees": 11,
        "find_callers": 11,
        "grep": 57,
        "read_paragraph": 92,
        "read_program": 50,
        "slice_on": 31,
        "trace_variable": 13
      }
    },
    "D7_conformant": {
      "answered": 14,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 93.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 888,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 697
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 47,
          "zero_values": 36
        },
        "find_callers": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 75,
          "zero_values": 58
        },
        "get_data_layout": {
          "maximum": 15.0,
          "median": 7.5,
          "samples": 2,
          "zero_values": 1
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 166,
          "zero_values": 151
        },
        "read_paragraph": {
          "maximum": 93.0,
          "median": 0.0,
          "samples": 306,
          "zero_values": 224
        },
        "read_program": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 195,
          "zero_values": 154
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 1,
          "zero_values": 1
        },
        "slice_on": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 73,
          "zero_values": 56
        },
        "trace_variable": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 23,
          "zero_values": 16
        }
      },
      "repeated_tool_arguments": 451,
      "rows": 43,
      "successful_observations": 888,
      "tool_calls": 888,
      "tools": {
        "find_callees": 47,
        "find_callers": 75,
        "get_data_layout": 2,
        "grep": 166,
        "read_paragraph": 306,
        "read_program": 195,
        "resolve_copybook": 1,
        "slice_on": 73,
        "trace_variable": 23
      }
    },
    "D7_conformant/interprocedural": {
      "answered": 2,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 93.0,
        "median": 16.0,
        "p95_nearest_rank": 62.0,
        "samples": 81,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 18
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 16.0,
          "samples": 4,
          "zero_values": 0
        },
        "find_callers": {
          "maximum": 31.0,
          "median": 16.0,
          "samples": 5,
          "zero_values": 0
        },
        "get_data_layout": {
          "maximum": 15.0,
          "median": 15.0,
          "samples": 1,
          "zero_values": 0
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 10,
          "zero_values": 6
        },
        "read_paragraph": {
          "maximum": 93.0,
          "median": 16.0,
          "samples": 42,
          "zero_values": 6
        },
        "read_program": {
          "maximum": 63.0,
          "median": 16.0,
          "samples": 13,
          "zero_values": 4
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 1,
          "zero_values": 1
        },
        "slice_on": {
          "maximum": 63.0,
          "median": 39.0,
          "samples": 4,
          "zero_values": 1
        },
        "trace_variable": {
          "maximum": 47.0,
          "median": 47.0,
          "samples": 1,
          "zero_values": 0
        }
      },
      "repeated_tool_arguments": 30,
      "rows": 4,
      "successful_observations": 81,
      "tool_calls": 81,
      "tools": {
        "find_callees": 4,
        "find_callers": 5,
        "get_data_layout": 1,
        "grep": 10,
        "read_paragraph": 42,
        "read_program": 13,
        "resolve_copybook": 1,
        "slice_on": 4,
        "trace_variable": 1
      }
    },
    "D7_conformant/local": {
      "answered": 12,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": 47.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 807,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 679
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 43,
          "zero_values": 36
        },
        "find_callers": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 70,
          "zero_values": 58
        },
        "get_data_layout": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 1,
          "zero_values": 1
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 156,
          "zero_values": 145
        },
        "read_paragraph": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 264,
          "zero_values": 218
        },
        "read_program": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 182,
          "zero_values": 150
        },
        "slice_on": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 69,
          "zero_values": 55
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 22,
          "zero_values": 16
        }
      },
      "repeated_tool_arguments": 421,
      "rows": 39,
      "successful_observations": 807,
      "tool_calls": 807,
      "tools": {
        "find_callees": 43,
        "find_callers": 70,
        "get_data_layout": 1,
        "grep": 156,
        "read_paragraph": 264,
        "read_program": 182,
        "slice_on": 69,
        "trace_variable": 22
      }
    },
    "interprocedural": {
      "answered": 14,
      "error_observations": 11,
      "host_observation_latency_ms": {
        "maximum": 203.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 739,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 593
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 39,
          "zero_values": 27
        },
        "find_callers": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 56,
          "zero_values": 44
        },
        "get_data_layout": {
          "maximum": 15.0,
          "median": 15.0,
          "samples": 1,
          "zero_values": 0
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 135,
          "zero_values": 117
        },
        "read_paragraph": {
          "maximum": 93.0,
          "median": 0.0,
          "samples": 263,
          "zero_values": 201
        },
        "read_program": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 141,
          "zero_values": 116
        },
        "resolve_copybook": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 37,
          "zero_values": 37
        },
        "run_cobol": {
          "maximum": 203.0,
          "median": 188.0,
          "samples": 3,
          "zero_values": 1
        },
        "slice_on": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 51,
          "zero_values": 39
        },
        "trace_variable": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 13,
          "zero_values": 11
        }
      },
      "repeated_tool_arguments": 344,
      "rows": 36,
      "successful_observations": 728,
      "tool_calls": 739,
      "tools": {
        "find_callees": 39,
        "find_callers": 56,
        "get_data_layout": 1,
        "grep": 135,
        "read_paragraph": 263,
        "read_program": 141,
        "resolve_copybook": 37,
        "run_cobol": 3,
        "slice_on": 51,
        "trace_variable": 13
      }
    },
    "local": {
      "answered": 96,
      "error_observations": 2,
      "host_observation_latency_ms": {
        "maximum": 1813.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 3273,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 2736
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 165,
          "zero_values": 138
        },
        "find_callers": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 270,
          "zero_values": 222
        },
        "get_data_layout": {
          "maximum": 0.0,
          "median": 0.0,
          "samples": 4,
          "zero_values": 4
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 626,
          "zero_values": 594
        },
        "read_paragraph": {
          "maximum": 62.0,
          "median": 0.0,
          "samples": 1093,
          "zero_values": 882
        },
        "read_program": {
          "maximum": 1813.0,
          "median": 0.0,
          "samples": 717,
          "zero_values": 594
        },
        "resolve_copybook": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 38,
          "zero_values": 35
        },
        "slice_on": {
          "maximum": 32.0,
          "median": 0.0,
          "samples": 270,
          "zero_values": 205
        },
        "trace_variable": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 90,
          "zero_values": 62
        }
      },
      "repeated_tool_arguments": 1749,
      "rows": 160,
      "successful_observations": 3271,
      "tool_calls": 3273,
      "tools": {
        "find_callees": 165,
        "find_callers": 270,
        "get_data_layout": 4,
        "grep": 626,
        "read_paragraph": 1093,
        "read_program": 717,
        "resolve_copybook": 38,
        "slice_on": 270,
        "trace_variable": 90
      }
    },
    "overall": {
      "answered": 110,
      "error_observations": 13,
      "host_observation_latency_ms": {
        "maximum": 1813.0,
        "median": 0.0,
        "p95_nearest_rank": 16.0,
        "samples": 4012,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 3329
      },
      "host_per_tool_latency_ms": {
        "find_callees": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 204,
          "zero_values": 165
        },
        "find_callers": {
          "maximum": 31.0,
          "median": 0.0,
          "samples": 326,
          "zero_values": 266
        },
        "get_data_layout": {
          "maximum": 15.0,
          "median": 0.0,
          "samples": 5,
          "zero_values": 4
        },
        "grep": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 761,
          "zero_values": 711
        },
        "read_paragraph": {
          "maximum": 93.0,
          "median": 0.0,
          "samples": 1356,
          "zero_values": 1083
        },
        "read_program": {
          "maximum": 1813.0,
          "median": 0.0,
          "samples": 858,
          "zero_values": 710
        },
        "resolve_copybook": {
          "maximum": 16.0,
          "median": 0.0,
          "samples": 75,
          "zero_values": 72
        },
        "run_cobol": {
          "maximum": 203.0,
          "median": 188.0,
          "samples": 3,
          "zero_values": 1
        },
        "slice_on": {
          "maximum": 63.0,
          "median": 0.0,
          "samples": 321,
          "zero_values": 244
        },
        "trace_variable": {
          "maximum": 47.0,
          "median": 0.0,
          "samples": 103,
          "zero_values": 73
        }
      },
      "repeated_tool_arguments": 2093,
      "rows": 196,
      "successful_observations": 3999,
      "tool_calls": 4012,
      "tools": {
        "find_callees": 204,
        "find_callers": 326,
        "get_data_layout": 5,
        "grep": 761,
        "read_paragraph": 1356,
        "read_program": 858,
        "resolve_copybook": 75,
        "run_cobol": 3,
        "slice_on": 321,
        "trace_variable": 103
      }
    }
  },
  "oracle_slice": {
    "D1_stale_threshold": {
      "answered": 23,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 61,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D1_stale_threshold/interprocedural": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 12,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D1_stale_threshold/local": {
      "answered": 23,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 49,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D2_missing_rule": {
      "answered": 5,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D2_missing_rule/local": {
      "answered": 5,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory": {
      "answered": 15,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 23,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory/interprocedural": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 8,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory/local": {
      "answered": 15,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 15,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D4_stale_reference_data": {
      "answered": 2,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D4_stale_reference_data/local": {
      "answered": 2,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D5_boundary_error": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 18,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D5_boundary_error/local": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 18,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code": {
      "answered": 1,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 23,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code/interprocedural": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 12,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code/local": {
      "answered": 1,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 11,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant": {
      "answered": 12,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 43,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant/interprocedural": {
      "answered": 1,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 4,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant/local": {
      "answered": 11,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 39,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "interprocedural": {
      "answered": 1,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 36,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "local": {
      "answered": 57,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 160,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "overall": {
      "answered": 58,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 196,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    }
  },
  "plain_llm": {
    "D1_stale_threshold": {
      "answered": 59,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 61,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D1_stale_threshold/interprocedural": {
      "answered": 12,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 12,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D1_stale_threshold/local": {
      "answered": 47,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 49,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D2_missing_rule": {
      "answered": 3,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D2_missing_rule/local": {
      "answered": 3,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory": {
      "answered": 15,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 23,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory/interprocedural": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 8,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory/local": {
      "answered": 15,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 15,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D4_stale_reference_data": {
      "answered": 5,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D4_stale_reference_data/local": {
      "answered": 5,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D5_boundary_error": {
      "answered": 17,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 18,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D5_boundary_error/local": {
      "answered": 17,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 18,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code": {
      "answered": 1,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 23,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code/interprocedural": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 12,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code/local": {
      "answered": 1,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 11,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant": {
      "answered": 18,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 43,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant/interprocedural": {
      "answered": 2,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 4,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant/local": {
      "answered": 16,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 39,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "interprocedural": {
      "answered": 14,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 36,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "local": {
      "answered": 104,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 160,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "overall": {
      "answered": 118,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 196,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    }
  },
  "rag_dense": {
    "D1_stale_threshold": {
      "answered": 53,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 61,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D1_stale_threshold/interprocedural": {
      "answered": 12,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 12,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D1_stale_threshold/local": {
      "answered": 41,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 49,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D2_missing_rule": {
      "answered": 8,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D2_missing_rule/local": {
      "answered": 8,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory": {
      "answered": 14,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 23,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory/interprocedural": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 8,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory/local": {
      "answered": 14,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 15,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D4_stale_reference_data": {
      "answered": 3,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D4_stale_reference_data/local": {
      "answered": 3,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D5_boundary_error": {
      "answered": 14,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 18,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D5_boundary_error/local": {
      "answered": 14,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 18,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 23,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code/interprocedural": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 12,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code/local": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 11,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant": {
      "answered": 14,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 43,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant/interprocedural": {
      "answered": 1,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 4,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant/local": {
      "answered": 13,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 39,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "interprocedural": {
      "answered": 13,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 36,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "local": {
      "answered": 93,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 160,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "overall": {
      "answered": 106,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 196,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    }
  },
  "rag_reranker": {
    "D1_stale_threshold": {
      "answered": 55,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 61,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D1_stale_threshold/interprocedural": {
      "answered": 12,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 12,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D1_stale_threshold/local": {
      "answered": 43,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 49,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D2_missing_rule": {
      "answered": 8,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D2_missing_rule/local": {
      "answered": 8,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory": {
      "answered": 15,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 23,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory/interprocedural": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 8,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D3_contradictory/local": {
      "answered": 15,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 15,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D4_stale_reference_data": {
      "answered": 3,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D4_stale_reference_data/local": {
      "answered": 3,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 14,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D5_boundary_error": {
      "answered": 17,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 18,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D5_boundary_error/local": {
      "answered": 17,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 18,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 23,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code/interprocedural": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 12,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D6_dead_code/local": {
      "answered": 0,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 11,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant": {
      "answered": 20,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 43,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant/interprocedural": {
      "answered": 1,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 4,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "D7_conformant/local": {
      "answered": 19,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 39,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "interprocedural": {
      "answered": 13,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 36,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "local": {
      "answered": 105,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 160,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    },
    "overall": {
      "answered": 118,
      "error_observations": 0,
      "host_observation_latency_ms": {
        "maximum": null,
        "median": null,
        "p95_nearest_rank": null,
        "samples": 0,
        "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
        "zero_values": 0
      },
      "host_per_tool_latency_ms": {},
      "repeated_tool_arguments": 0,
      "rows": 196,
      "successful_observations": 0,
      "tool_calls": 0,
      "tools": {}
    }
  }
}
```

## Temporal host observations

Evidence: `performance-profile.json:/temporal_host_observations`

```json
{
  "D1_stale_threshold": {
    "answered": 5,
    "error_observations": 8,
    "host_observation_latency_ms": {
      "maximum": 31.0,
      "median": 0.0,
      "p95_nearest_rank": 16.0,
      "samples": 77,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 70
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 25,
        "zero_values": 25
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 19,
        "zero_values": 16
      },
      "read_program": {
        "maximum": 31.0,
        "median": 0.0,
        "samples": 15,
        "zero_values": 13
      },
      "slice_on": {
        "maximum": 15.0,
        "median": 0.0,
        "samples": 8,
        "zero_values": 6
      },
      "trace_variable": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 10,
        "zero_values": 10
      }
    },
    "repeated_tool_arguments": 4,
    "rows": 10,
    "successful_observations": 69,
    "tool_calls": 77,
    "tools": {
      "grep": 25,
      "read_paragraph": 19,
      "read_program": 15,
      "slice_on": 8,
      "trace_variable": 10
    }
  },
  "D1_stale_threshold/interprocedural": {
    "answered": 0,
    "error_observations": 3,
    "host_observation_latency_ms": {
      "maximum": 31.0,
      "median": 0.0,
      "p95_nearest_rank": 31.0,
      "samples": 14,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 13
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 8,
        "zero_values": 8
      },
      "read_paragraph": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 3,
        "zero_values": 3
      },
      "read_program": {
        "maximum": 31.0,
        "median": 15.5,
        "samples": 2,
        "zero_values": 1
      },
      "trace_variable": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      }
    },
    "repeated_tool_arguments": 1,
    "rows": 1,
    "successful_observations": 11,
    "tool_calls": 14,
    "tools": {
      "grep": 8,
      "read_paragraph": 3,
      "read_program": 2,
      "trace_variable": 1
    }
  },
  "D1_stale_threshold/local": {
    "answered": 5,
    "error_observations": 5,
    "host_observation_latency_ms": {
      "maximum": 16.0,
      "median": 0.0,
      "p95_nearest_rank": 15.0,
      "samples": 63,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 57
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 17,
        "zero_values": 17
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 16,
        "zero_values": 13
      },
      "read_program": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 13,
        "zero_values": 12
      },
      "slice_on": {
        "maximum": 15.0,
        "median": 0.0,
        "samples": 8,
        "zero_values": 6
      },
      "trace_variable": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 9,
        "zero_values": 9
      }
    },
    "repeated_tool_arguments": 3,
    "rows": 9,
    "successful_observations": 58,
    "tool_calls": 63,
    "tools": {
      "grep": 17,
      "read_paragraph": 16,
      "read_program": 13,
      "slice_on": 8,
      "trace_variable": 9
    }
  },
  "D2_missing_rule": {
    "answered": 7,
    "error_observations": 5,
    "host_observation_latency_ms": {
      "maximum": 46.0,
      "median": 0.0,
      "p95_nearest_rank": 16.0,
      "samples": 72,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 55
    },
    "host_per_tool_latency_ms": {
      "get_data_layout": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "grep": {
        "maximum": 15.0,
        "median": 0.0,
        "samples": 19,
        "zero_values": 18
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 21,
        "zero_values": 16
      },
      "read_program": {
        "maximum": 46.0,
        "median": 0.0,
        "samples": 11,
        "zero_values": 6
      },
      "run_cobol": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "slice_on": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 18,
        "zero_values": 12
      },
      "trace_variable": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      }
    },
    "repeated_tool_arguments": 4,
    "rows": 9,
    "successful_observations": 67,
    "tool_calls": 72,
    "tools": {
      "get_data_layout": 1,
      "grep": 19,
      "read_paragraph": 21,
      "read_program": 11,
      "run_cobol": 1,
      "slice_on": 18,
      "trace_variable": 1
    }
  },
  "D2_missing_rule/interprocedural": {
    "answered": 0,
    "error_observations": 3,
    "host_observation_latency_ms": {
      "maximum": 16.0,
      "median": 0.0,
      "p95_nearest_rank": 16.0,
      "samples": 10,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 6
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 2,
        "zero_values": 2
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 8.0,
        "samples": 2,
        "zero_values": 1
      },
      "read_program": {
        "maximum": 16.0,
        "median": 8.0,
        "samples": 2,
        "zero_values": 1
      },
      "run_cobol": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "slice_on": {
        "maximum": 16.0,
        "median": 15.5,
        "samples": 2,
        "zero_values": 0
      },
      "trace_variable": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      }
    },
    "repeated_tool_arguments": 0,
    "rows": 1,
    "successful_observations": 7,
    "tool_calls": 10,
    "tools": {
      "grep": 2,
      "read_paragraph": 2,
      "read_program": 2,
      "run_cobol": 1,
      "slice_on": 2,
      "trace_variable": 1
    }
  },
  "D2_missing_rule/local": {
    "answered": 7,
    "error_observations": 2,
    "host_observation_latency_ms": {
      "maximum": 46.0,
      "median": 0.0,
      "p95_nearest_rank": 16.0,
      "samples": 62,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 49
    },
    "host_per_tool_latency_ms": {
      "get_data_layout": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "grep": {
        "maximum": 15.0,
        "median": 0.0,
        "samples": 17,
        "zero_values": 16
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 19,
        "zero_values": 15
      },
      "read_program": {
        "maximum": 46.0,
        "median": 0.0,
        "samples": 9,
        "zero_values": 5
      },
      "slice_on": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 16,
        "zero_values": 12
      }
    },
    "repeated_tool_arguments": 4,
    "rows": 8,
    "successful_observations": 60,
    "tool_calls": 62,
    "tools": {
      "get_data_layout": 1,
      "grep": 17,
      "read_paragraph": 19,
      "read_program": 9,
      "slice_on": 16
    }
  },
  "D5_boundary_error": {
    "answered": 1,
    "error_observations": 1,
    "host_observation_latency_ms": {
      "maximum": 15.0,
      "median": 0.0,
      "p95_nearest_rank": 15.0,
      "samples": 6,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 5
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 2,
        "zero_values": 2
      },
      "read_paragraph": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "read_program": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 2,
        "zero_values": 2
      },
      "slice_on": {
        "maximum": 15.0,
        "median": 15.0,
        "samples": 1,
        "zero_values": 0
      }
    },
    "repeated_tool_arguments": 0,
    "rows": 1,
    "successful_observations": 5,
    "tool_calls": 6,
    "tools": {
      "grep": 2,
      "read_paragraph": 1,
      "read_program": 2,
      "slice_on": 1
    }
  },
  "D5_boundary_error/local": {
    "answered": 1,
    "error_observations": 1,
    "host_observation_latency_ms": {
      "maximum": 15.0,
      "median": 0.0,
      "p95_nearest_rank": 15.0,
      "samples": 6,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 5
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 2,
        "zero_values": 2
      },
      "read_paragraph": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "read_program": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 2,
        "zero_values": 2
      },
      "slice_on": {
        "maximum": 15.0,
        "median": 15.0,
        "samples": 1,
        "zero_values": 0
      }
    },
    "repeated_tool_arguments": 0,
    "rows": 1,
    "successful_observations": 5,
    "tool_calls": 6,
    "tools": {
      "grep": 2,
      "read_paragraph": 1,
      "read_program": 2,
      "slice_on": 1
    }
  },
  "D7_conformant": {
    "answered": 16,
    "error_observations": 12,
    "host_observation_latency_ms": {
      "maximum": 16.0,
      "median": 0.0,
      "p95_nearest_rank": 16.0,
      "samples": 139,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 115
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 41,
        "zero_values": 38
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 37,
        "zero_values": 29
      },
      "read_program": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 29,
        "zero_values": 25
      },
      "slice_on": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 20,
        "zero_values": 17
      },
      "trace_variable": {
        "maximum": 16.0,
        "median": 7.5,
        "samples": 12,
        "zero_values": 6
      }
    },
    "repeated_tool_arguments": 1,
    "rows": 20,
    "successful_observations": 127,
    "tool_calls": 139,
    "tools": {
      "grep": 41,
      "read_paragraph": 37,
      "read_program": 29,
      "slice_on": 20,
      "trace_variable": 12
    }
  },
  "D7_conformant/interprocedural": {
    "answered": 1,
    "error_observations": 4,
    "host_observation_latency_ms": {
      "maximum": 15.0,
      "median": 0.0,
      "p95_nearest_rank": 15.0,
      "samples": 19,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 18
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 8,
        "zero_values": 8
      },
      "read_paragraph": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 4,
        "zero_values": 4
      },
      "read_program": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 4,
        "zero_values": 4
      },
      "slice_on": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 2,
        "zero_values": 2
      },
      "trace_variable": {
        "maximum": 15.0,
        "median": 15.0,
        "samples": 1,
        "zero_values": 0
      }
    },
    "repeated_tool_arguments": 0,
    "rows": 2,
    "successful_observations": 15,
    "tool_calls": 19,
    "tools": {
      "grep": 8,
      "read_paragraph": 4,
      "read_program": 4,
      "slice_on": 2,
      "trace_variable": 1
    }
  },
  "D7_conformant/local": {
    "answered": 15,
    "error_observations": 8,
    "host_observation_latency_ms": {
      "maximum": 16.0,
      "median": 0.0,
      "p95_nearest_rank": 16.0,
      "samples": 120,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 97
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 33,
        "zero_values": 30
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 33,
        "zero_values": 25
      },
      "read_program": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 25,
        "zero_values": 21
      },
      "slice_on": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 18,
        "zero_values": 15
      },
      "trace_variable": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 11,
        "zero_values": 6
      }
    },
    "repeated_tool_arguments": 1,
    "rows": 18,
    "successful_observations": 112,
    "tool_calls": 120,
    "tools": {
      "grep": 33,
      "read_paragraph": 33,
      "read_program": 25,
      "slice_on": 18,
      "trace_variable": 11
    }
  },
  "interprocedural": {
    "answered": 1,
    "error_observations": 10,
    "host_observation_latency_ms": {
      "maximum": 31.0,
      "median": 0.0,
      "p95_nearest_rank": 16.0,
      "samples": 43,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 37
    },
    "host_per_tool_latency_ms": {
      "grep": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 18,
        "zero_values": 18
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 9,
        "zero_values": 8
      },
      "read_program": {
        "maximum": 31.0,
        "median": 0.0,
        "samples": 8,
        "zero_values": 6
      },
      "run_cobol": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "slice_on": {
        "maximum": 16.0,
        "median": 7.5,
        "samples": 4,
        "zero_values": 2
      },
      "trace_variable": {
        "maximum": 15.0,
        "median": 0.0,
        "samples": 3,
        "zero_values": 2
      }
    },
    "repeated_tool_arguments": 1,
    "rows": 4,
    "successful_observations": 33,
    "tool_calls": 43,
    "tools": {
      "grep": 18,
      "read_paragraph": 9,
      "read_program": 8,
      "run_cobol": 1,
      "slice_on": 4,
      "trace_variable": 3
    }
  },
  "local": {
    "answered": 28,
    "error_observations": 16,
    "host_observation_latency_ms": {
      "maximum": 46.0,
      "median": 0.0,
      "p95_nearest_rank": 16.0,
      "samples": 251,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 208
    },
    "host_per_tool_latency_ms": {
      "get_data_layout": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "grep": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 69,
        "zero_values": 65
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 69,
        "zero_values": 54
      },
      "read_program": {
        "maximum": 46.0,
        "median": 0.0,
        "samples": 49,
        "zero_values": 40
      },
      "slice_on": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 43,
        "zero_values": 33
      },
      "trace_variable": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 20,
        "zero_values": 15
      }
    },
    "repeated_tool_arguments": 8,
    "rows": 36,
    "successful_observations": 235,
    "tool_calls": 251,
    "tools": {
      "get_data_layout": 1,
      "grep": 69,
      "read_paragraph": 69,
      "read_program": 49,
      "slice_on": 43,
      "trace_variable": 20
    }
  },
  "overall": {
    "answered": 29,
    "error_observations": 26,
    "host_observation_latency_ms": {
      "maximum": 46.0,
      "median": 0.0,
      "p95_nearest_rank": 16.0,
      "samples": 294,
      "scope": "Recorded host step latencies, including zero/error placeholders; no provider end-to-end inference",
      "zero_values": 245
    },
    "host_per_tool_latency_ms": {
      "get_data_layout": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "grep": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 87,
        "zero_values": 83
      },
      "read_paragraph": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 78,
        "zero_values": 62
      },
      "read_program": {
        "maximum": 46.0,
        "median": 0.0,
        "samples": 57,
        "zero_values": 46
      },
      "run_cobol": {
        "maximum": 0.0,
        "median": 0.0,
        "samples": 1,
        "zero_values": 1
      },
      "slice_on": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 47,
        "zero_values": 35
      },
      "trace_variable": {
        "maximum": 16.0,
        "median": 0.0,
        "samples": 23,
        "zero_values": 17
      }
    },
    "repeated_tool_arguments": 9,
    "rows": 40,
    "successful_observations": 268,
    "tool_calls": 294,
    "tools": {
      "get_data_layout": 1,
      "grep": 87,
      "read_paragraph": 78,
      "read_program": 57,
      "run_cobol": 1,
      "slice_on": 47,
      "trace_variable": 23
    }
  }
}
```

## Coverage gained

Evidence: `performance-profile.json:/coverage_gain`

```json
{
  "interprocedural": {
    "adaptive_coverage": 0.6111111111111112,
    "additional_host_tool_calls": -374,
    "causal_interpretation": "Descriptive system comparison, no marginal causal tool benefit",
    "coverage_difference": 0.2222222222222222,
    "historical_control_coverage": 0.3888888888888889
  },
  "local": {
    "adaptive_coverage": 0.73125,
    "additional_host_tool_calls": -2226,
    "causal_interpretation": "Descriptive system comparison, no marginal causal tool benefit",
    "coverage_difference": 0.13125,
    "historical_control_coverage": 0.6
  },
  "overall": {
    "adaptive_coverage": 0.7091836734693877,
    "additional_host_tool_calls": -2600,
    "causal_interpretation": "Descriptive system comparison, no marginal causal tool benefit",
    "coverage_difference": 0.14795918367346939,
    "historical_control_coverage": 0.5612244897959183
  }
}
```

## Missing provider measurements

Evidence: `performance-profile.json:/resource_telemetry`

```json
{
  "complete_provider_retry_count": "not_recorded",
  "metered_billing": "not_recorded",
  "provider_cache_reads": "not_recorded",
  "provider_cache_writes": "not_recorded",
  "provider_end_to_end_latency": "not_recorded",
  "provider_per_tool_latency": "not_recorded",
  "provider_tokens": "not_recorded",
  "provider_turns": "not_recorded"
}
```

## Retries and resumptions

Evidence: `performance-profile.json:/retry_accounting`

```json
"Preserved diagnostic files and interruption registry; not a complete provider attempt count. Counted repair substitutions remain separately zero."
```

## Latency limitation

Evidence: `performance-profile.json:/latency_limitation`

```json
"Trajectory latency_ms can include zero/error placeholders; no end-to-end or per-tool latency advantage is asserted."
```

## Cache limitation

Evidence: `performance-profile.json:/cache_limitation`

```json
"Repeated same-tool arguments are observed within rows; they do not prove provider cache hits or misses."
```

## Billing

Evidence: `performance-profile.json:/billing_claim`

```json
"No dollar cost inferred without metered billing evidence"
```
