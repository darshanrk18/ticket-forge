"""Great Expectations integration for schema validation."""

import great_expectations as gx
import pandas as pd


class GreatExpectationsValidator:
  """Schema validation using Great Expectations."""

  def __init__(self) -> None:
    """Initialize GE validator."""
    self.context = gx.get_context()
    self.suite = gx.ExpectationSuite(name="ticket_data_suite")
    self.context.suites.add(self.suite)

  def create_expectations(self, data: pd.DataFrame) -> None:
    """Create expectations from data."""
    for column in data.columns:
      self.suite.add_expectation(gx.expectations.ExpectColumnToExist(column=column))  # type: ignore[attr-defined]

      null_pct = data[column].isnull().sum() / len(data)
      if null_pct < 0.05:
        self.suite.add_expectation(
          gx.expectations.ExpectColumnValuesToNotBeNull(column=column)  # type: ignore[attr-defined]
        )

  def validate_data(self, data: pd.DataFrame) -> dict:
    """Validate data against expectations."""
    datasource = self.context.data_sources.add_pandas("pandas_datasource")
    data_asset = datasource.add_dataframe_asset(name="tickets")
    batch_definition = data_asset.add_batch_definition_whole_dataframe("batch_def")

    batch_params = {"dataframe": data}

    validation_definition = gx.ValidationDefinition(
      data=batch_definition, suite=self.suite, name="validation"
    )
    self.context.validation_definitions.add(validation_definition)

    results = validation_definition.run(batch_parameters=batch_params)

    failed_count = sum(1 for r in results.results if not r.success)

    return {
      "success": results.success,
      "total_expectations": len(results.results),
      "failed_expectations": failed_count,
    }

  def save_schema(self, output_path: str) -> None:
    """Save schema to file."""
    import json

    with open(output_path, "w") as f:
      json.dump(self.suite.to_json_dict(), f, indent=2)

    print("Schema saved to", output_path)
