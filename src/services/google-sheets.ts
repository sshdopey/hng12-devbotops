import { google, sheets_v4 } from 'googleapis';
import { logger } from '@/config';
import { ExternalServiceError } from '@/types';

interface SheetConfig {
  readonly spreadsheetId: string;
  readonly columns: Record<string, string>;
}

interface SheetRow {
  readonly rowNumber: number;
  readonly data: Record<string, string>;
}

export class GoogleSheetService {
  private readonly service: sheets_v4.Sheets;
  private readonly columnReverse: Record<string, string>;

  constructor(
    private readonly config: SheetConfig,
    private readonly credentialsPath: string = 'token.json'
  ) {
    this.columnReverse = Object.fromEntries(
      Object.entries(config.columns).map(([letter, name]) => [name, letter])
    );
    this.service = this.initializeService();
  }

  private initializeService(): sheets_v4.Sheets {
    try {
      const auth = new google.auth.GoogleAuth({
        keyFile: this.credentialsPath,
        scopes: ['https://www.googleapis.com/auth/spreadsheets'],
      });

      return google.sheets({ version: 'v4', auth });
    } catch (error) {
      throw new ExternalServiceError(
        `Failed to initialize Google Sheets service: ${error instanceof Error ? error.message : String(error)}`,
        'GoogleSheets'
      );
    }
  }

  /**
   * Get a row by searching for a value in a specific column
   */
  async getRow(columnName: string, searchValue: string): Promise<SheetRow | null> {
    if (!(columnName in this.columnReverse)) {
      throw new Error(`Column ${columnName} not found in column mappings`);
    }

    try {
      const columnLetter = this.columnReverse[columnName]!;
      const response = await this.service.spreadsheets.values.get({
        spreadsheetId: this.config.spreadsheetId,
        range: 'A1:Z',
      });

      const values = response.data.values ?? [];
      
      for (let rowIndex = 0; rowIndex < values.length; rowIndex++) {
        const row = values[rowIndex] ?? [];
        const colIndex = columnLetter.charCodeAt(0) - 'A'.charCodeAt(0);
        
        if (colIndex < row.length && row[colIndex] === searchValue) {
          const rowData: Record<string, string> = {};
          
          for (const [letter, name] of Object.entries(this.config.columns)) {
            const index = letter.charCodeAt(0) - 'A'.charCodeAt(0);
            rowData[name] = index < row.length ? row[index] ?? '' : '';
          }
          
          return {
            rowNumber: rowIndex + 1,
            data: rowData,
          };
        }
      }
      
      return null;
    } catch (error) {
      logger.error('Error getting row from sheet:', error);
      throw new ExternalServiceError(
        `Failed to get row from sheet: ${error instanceof Error ? error.message : String(error)}`,
        'GoogleSheets'
      );
    }
  }

  /**
   * Update specific cells in a row using column mappings
   */
  async updateRow(rowNumber: number, data: Record<string, string>): Promise<void> {
    try {
      const updates: { range: string; values: string[][] }[] = [];

      for (const [columnName, value] of Object.entries(data)) {
        if (!(columnName in this.columnReverse)) {
          throw new Error(`Column ${columnName} not found in column mappings`);
        }
        
        const columnLetter = this.columnReverse[columnName];
        const cell = `${columnLetter}${rowNumber}`;
        updates.push({ range: cell, values: [[value]] });
      }

      await this.service.spreadsheets.values.batchUpdate({
        spreadsheetId: this.config.spreadsheetId,
        requestBody: {
          valueInputOption: 'RAW',
          data: updates,
        },
      });

      logger.debug(`Updated row ${rowNumber} with data:`, data);
    } catch (error) {
      logger.error('Error updating row in sheet:', error);
      throw new ExternalServiceError(
        `Failed to update row in sheet: ${error instanceof Error ? error.message : String(error)}`,
        'GoogleSheets'
      );
    }
  }

  /**
   * Append a new row using column mappings
   */
  async appendRow(data: Record<string, string>): Promise<void> {
    try {
      const maxColumnIndex = Math.max(
        ...Object.keys(this.config.columns).map(col => col.charCodeAt(0) - 'A'.charCodeAt(0))
      );
      const row: string[] = new Array(maxColumnIndex + 1).fill('');

      for (const [columnName, value] of Object.entries(data)) {
        if (!(columnName in this.columnReverse)) {
          throw new Error(`Column ${columnName} not found in column mappings`);
        }
        
        const columnIndex = this.columnReverse[columnName]!.charCodeAt(0) - 'A'.charCodeAt(0);
        row[columnIndex] = value;
      }

      await this.service.spreadsheets.values.append({
        spreadsheetId: this.config.spreadsheetId,
        range: 'A1',
        valueInputOption: 'RAW',
        insertDataOption: 'INSERT_ROWS',
        requestBody: {
          values: [row],
        },
      });

      logger.debug('Appended new row with data:', data);
    } catch (error) {
      logger.error('Error appending row to sheet:', error);
      throw new ExternalServiceError(
        `Failed to append row to sheet: ${error instanceof Error ? error.message : String(error)}`,
        'GoogleSheets'
      );
    }
  }

  /**
   * Get all values from the sheet
   */
  async getAllValues(): Promise<string[][]> {
    try {
      const response = await this.service.spreadsheets.values.get({
        spreadsheetId: this.config.spreadsheetId,
        range: 'A1:Z',
      });

      return response.data.values ?? [];
    } catch (error) {
      logger.error('Error getting all values from sheet:', error);
      throw new ExternalServiceError(
        `Failed to get all values from sheet: ${error instanceof Error ? error.message : String(error)}`,
        'GoogleSheets'
      );
    }
  }
}