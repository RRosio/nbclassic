import os

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement

from contextlib import contextmanager

pjoin = os.path.join


def wait_for_selector(browser, selector, timeout=10, visible=False, single=False):
    wait = WebDriverWait(browser, timeout)
    if single:
        if visible:
            conditional = EC.visibility_of_element_located
        else:
            conditional = EC.presence_of_element_located
    else:
        if visible:
            conditional = EC.visibility_of_all_elements_located
        else:
            conditional = EC.presence_of_all_elements_located
    return wait.until(conditional((By.CSS_SELECTOR, selector)))


class CellTypeError(ValueError):
    
    def __init__(self, message=""):
        self.message = message


class Notebook:
    
    def __init__(self, browser):
        self.browser = browser
        self.disable_autosave_and_onbeforeunload()
        
    def __len__(self):
        return len(self.cells)
        
    def __getitem__(self, key):
        return self.cells[key]
    
    def __setitem__(self, key, item):
        if isinstance(key, int):
            self.edit_cell(index=key, content=item, render=False)
        # TODO: re-add slicing support, handle general python slicing behaviour
        # includes: overwriting the entire self.cells object if you do 
        # self[:] = []
        # elif isinstance(key, slice):
        #     indices = (self.index(cell) for cell in self[key])
        #     for k, v in zip(indices, item):
        #         self.edit_cell(index=k, content=v, render=False)

    def __iter__(self):
        return (cell for cell in self.cells)

    @property
    def body(self):
        return self.browser.find_element_by_tag_name("body")

    @property
    def cells(self):
        """Gets all cells once they are visible.
        
        """
        return self.browser.find_elements_by_class_name("cell")

    @property
    def current_index(self):
        return self.index(self.current_cell)
    
    def index(self, cell):
        return self.cells.index(cell)

    def disable_autosave_and_onbeforeunload(self):
        """Disable request to save before closing window and autosave.
        
        This is most easily done by using js directly.
        """
        self.browser.execute_script("window.onbeforeunload = null;")
        self.browser.execute_script("Jupyter.notebook.set_autosave_interval(0)")

    def to_command_mode(self):
        """Changes us into command mode on currently focused cell
        
        """
        self.body.send_keys(Keys.ESCAPE)
        self.browser.execute_script("return Jupyter.notebook.handle_command_mode("
                                       "Jupyter.notebook.get_cell("
                                           "Jupyter.notebook.get_edit_index()))")

    def focus_cell(self, index=0):
        cell = self.cells[index]
        cell.click()
        self.to_command_mode()
        self.current_cell = cell

    def convert_cell_type(self, index=0, cell_type="code"):
        # TODO add check to see if it is already present
        self.focus_cell(index)
        cell = self.cells[index]
        if cell_type == "markdown":
            self.current_cell.send_keys("m")
        elif cell_type == "raw":
            self.current_cell.send_keys("r")
        elif cell_type == "code":
            self.current_cell.send_keys("y")
        else:
            raise CellTypeError(("{} is not a valid cell type,"
                                 "use 'code', 'markdown', or 'raw'").format(cell_type))
                                 
        self.wait_for_stale_cell(cell)
        self.focus_cell(index)
        return self.current_cell

    def wait_for_stale_cell(self, cell):
        """ This is needed to switch a cell's mode and refocus it, or to render it.

        Warning: there is currently no way to do this when changing between 
        markdown and raw cells.
        """
        wait = WebDriverWait(self.browser, 10)
        element = wait.until(EC.staleness_of(cell))

    def edit_cell(self, cell=None, index=0, content="", render=False):
        if cell is not None:
            index = self.index(cell)
        self.focus_cell(index)

        for line_no, line in enumerate(content.splitlines()):
            if line_no != 0:
                self.current_cell.send_keys(Keys.ENTER, "\n")
            self.current_cell.send_keys(Keys.ENTER, line)
        if render:
            self.execute_cell(self.current_index)

    def execute_cell(self, cell_or_index=None):
        if isinstance(cell_or_index, int):
            index = cell_or_index
        elif isinstance(cell_or_index, WebElement): 
            index = self.index(cell_or_index)
        else:
            raise TypeError("execute_cell only accepts a WebElement or an int")
        self.focus_cell(index)
        self.current_cell.send_keys(Keys.CONTROL, Keys.ENTER)

    def add_cell(self, index=-1, cell_type="code", content=""):
        self.focus_cell(index)
        self.current_cell.send_keys("b")
        new_index = index + 1 if index >= 0 else index
        if content:
            self.edit_cell(index=index, content=content)
        self.convert_cell_type(index=new_index, cell_type=cell_type)

    def add_markdown_cell(self, index=-1, content="", render=True):
        self.add_cell(index, cell_type="markdown")
        self.edit_cell(index=index, content=content, render=render)
    
    def append(self, *values, cell_type="code"):
        for i, value in enumerate(values):
            if isinstance(value, str):
                self.add_cell(cell_type=cell_type,
                              content=value)
            else:
                raise TypeError("Don't know how to add cell from %r" % value)
    
    def extend(self, values):
        self.append(*values)
    
    def run_all(self):
        for cell in self:
            self.execute_cell(cell)

    @classmethod
    def new_notebook(cls, browser, kernel_name='kernel-python3'):
        with new_window(browser, selector=".cell"):
            select_kernel(browser, kernel_name=kernel_name)
        return cls(browser)

    
def select_kernel(browser, kernel_name='kernel-python3'):
    """Clicks the "new" button and selects a kernel from the options.
    """
    new_button = wait_for_selector(browser, "#new-buttons", single=True)
    new_button.click()
    kernel_selector = '#{} a'.format(kernel_name)
    kernel = wait_for_selector(browser, kernel_selector, single=True)
    kernel.click()

@contextmanager
def new_window(browser, selector=None):
    """Contextmanager for switching to & waiting for a window created. 
    
    This context manager gives you the ability to create a new window inside 
    the created context and it will switch you to that new window.
    
    If you know a CSS selector that can be expected to appear on the window, 
    then this utility can wait on that selector appearing on the page before
    releasing the context.
    
    Usage example:
    
        from notebook.tests.selenium.utils import new_window, Notebook
        
        ⋮ # something that creates a browser object
        
        with new_window(browser, selector=".cell"):
            select_kernel(browser, kernel_name=kernel_name)
        nb = Notebook(browser)

    """
    initial_window_handles = browser.window_handles
    yield
    new_window_handle = next(window for window in browser.window_handles 
                             if window not in initial_window_handles)
    browser.switch_to_window(new_window_handle)
    if selector is not None:
        wait_for_selector(browser, selector)
