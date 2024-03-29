import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
import glob
import os
import math
import warnings


class AutoScrollbar(ttk.Scrollbar):
    """ A scrollbar that hides itself if it's not needed. Works only for grid geometry manager """
    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.grid_remove()
        else:
            self.grid()
            ttk.Scrollbar.set(self, lo, hi)

class CanvasImage:
    """ Display and zoom image """
    def __init__(self, placeholder, path):
        """ Initialize the ImageFrame """
        self.imscale = 1.0  # scale for the canvas image zoom, public for outer classes
        self.__delta = 1.3  # zoom magnitude
        self.__filter = Image.ANTIALIAS  # could be: NEAREST, BILINEAR, BICUBIC and ANTIALIAS
        self.__previous_state = 0  # previous state of the keyboard
        self.path = path  # path to the image, should be public for outer classes
        # Create ImageFrame in placeholder widget
        self.parent_container = placeholder
        self.__imframe = ttk.Frame(placeholder)  # placeholder of the ImageFrame object
        # Vertical and horizontal scrollbars for canvas
        self.hbar = AutoScrollbar(self.__imframe, orient='horizontal')
        self.vbar = AutoScrollbar(self.__imframe, orient='vertical')
        self.hbar.grid(row=1, column=0, sticky='we')
        self.vbar.grid(row=0, column=1, sticky='ns')
        # Create canvas and bind it with scrollbars. Public for outer classes
        self.canvas = tk.Canvas(self.__imframe, highlightthickness=0,
                                xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.canvas.grid(row=0, column=0, sticky='nswe')
        self.canvas.update()  # wait till canvas is created
        self.hbar.configure(command=self.__scroll_x)  # bind scrollbars to the canvas
        self.vbar.configure(command=self.__scroll_y)
        # Bind events to the Canvas
        self.canvas.bind('<Configure>', lambda event: self.__show_image())  # canvas is resized
        self.canvas.bind('<ButtonPress-1>', self.__move_from)  # remember canvas position
        self.canvas.bind('<B1-Motion>',     self.__move_to)  # move canvas to the new position
        self.canvas.bind('<MouseWheel>', self.__wheel)  # zoom for Windows and MacOS, but not Linux
        self.canvas.bind('<Button-5>',   self.__wheel)  # zoom for Linux, wheel scroll down
        self.canvas.bind('<Button-4>',   self.__wheel)  # zoom for Linux, wheel scroll up
        self.canvas.bind("<ButtonRelease-1>", self.__on_release)
        # Handle keystrokes in idle mode, because program slows down on a weak computers,
        # when too many key stroke events in the same time
        self.canvas.bind('<Key>', lambda event: self.canvas.after_idle(self.__keystroke, event))
        # Decide if this image huge or not
        self.__huge = False  # huge or not
        self.__huge_size = 14000  # define size of the huge image
        self.__band_width = 1024  # width of the tile band
        Image.MAX_IMAGE_PIXELS = 1000000000  # suppress DecompressionBombError for the big image
        with warnings.catch_warnings():  # suppress DecompressionBombWarning
            warnings.simplefilter('ignore')
            self.__image = Image.open(self.path)  # open image, but down't load it
        self.imwidth, self.imheight = self.__image.size  # public for outer classes
        if self.imwidth * self.imheight > self.__huge_size * self.__huge_size and \
           self.__image.tile[0][0] == 'raw':  # only raw images could be tiled
            self.__huge = True  # image is huge
            self.__offset = self.__image.tile[0][2]  # initial tile offset
            self.__tile = [self.__image.tile[0][0],  # it have to be 'raw'
                           [0, 0, self.imwidth, 0],  # tile extent (a rectangle)
                           self.__offset,
                           self.__image.tile[0][3]]  # list of arguments to the decoder
        self.__min_side = min(self.imwidth, self.imheight)  # get the smaller image side
        # Create image pyramid
        self.__pyramid = [self.smaller()] if self.__huge else [Image.open(self.path)]
        # Set ratio coefficient for image pyramid
        self.__ratio = max(self.imwidth, self.imheight) / self.__huge_size if self.__huge else 1.0
        self.__curr_img = 0  # current image from the pyramid
        self.__scale = self.imscale * self.__ratio  # image pyramide scale
        self.__reduction = 2  # reduction degree of image pyramid
        w, h = self.__pyramid[-1].size
        while w > 512 and h > 512:  # top pyramid image is around 512 pixels in size
            w /= self.__reduction  # divide on reduction degree
            h /= self.__reduction  # divide on reduction degree
            self.__pyramid.append(self.__pyramid[-1].resize((int(w), int(h)), self.__filter))
        # Put image into container rectangle and use it to set proper coordinates to the image
        self.container = self.canvas.create_rectangle((0, 0, self.imwidth, self.imheight), width=0)

        if self.parent_container.labels_created != []:
            for label in self.parent_container.labels_created:
                label.rectangle_drawn = self.canvas.create_rectangle(label.x, label.y, label.x1, label.y1, outline="green2")
                label.text_drawn = self.canvas.create_text(label.x, label.y, text=label.type, fill="green2")

        self.__show_image()  # show image on the canvas
        self.canvas.focus_set()  # set focus on the canvas

    def smaller(self):
        """ Resize image proportionally and return smaller image """
        w1, h1 = float(self.imwidth), float(self.imheight)
        w2, h2 = float(self.__huge_size), float(self.__huge_size)
        aspect_ratio1 = w1 / h1
        aspect_ratio2 = w2 / h2  # it equals to 1.0
        if aspect_ratio1 == aspect_ratio2:
            image = Image.new('RGB', (int(w2), int(h2)))
            k = h2 / h1  # compression ratio
            w = int(w2)  # band length
        elif aspect_ratio1 > aspect_ratio2:
            image = Image.new('RGB', (int(w2), int(w2 / aspect_ratio1)))
            k = h2 / w1  # compression ratio
            w = int(w2)  # band length
        else:  # aspect_ratio1 < aspect_ration2
            image = Image.new('RGB', (int(h2 * aspect_ratio1), int(h2)))
            k = h2 / h1  # compression ratio
            w = int(h2 * aspect_ratio1)  # band length
        i, j, n = 0, 1, round(0.5 + self.imheight / self.__band_width)
        while i < self.imheight:
            print('\rOpening image: {j} from {n}'.format(j=j, n=n), end='')
            band = min(self.__band_width, self.imheight - i)  # width of the tile band
            self.__tile[1][3] = band  # set band width
            self.__tile[2] = self.__offset + self.imwidth * i * 3  # tile offset (3 bytes per pixel)
            self.__image.close()
            self.__image = Image.open(self.path)  # reopen / reset image
            self.__image.size = (self.imwidth, band)  # set size of the tile band
            self.__image.tile = [self.__tile]  # set tile
            cropped = self.__image.crop((0, 0, self.imwidth, band))  # crop tile band
            image.paste(cropped.resize((w, int(band * k)+1), self.__filter), (0, int(i * k)))
            i += band
            j += 1
        print('\r' + 30*' ' + '\r', end='')  # hide printed string
        return image

    def redraw_figures(self):
        """ Dummy function to redraw figures in the children classes """
        pass

    def grid(self, **kw):
        """ Put CanvasImage widget on the parent widget """
        self.__imframe.grid(**kw)  # place CanvasImage widget on the grid
        self.__imframe.grid(sticky='nswe')  # make frame container sticky
        self.__imframe.rowconfigure(0, weight=1)  # make canvas expandable
        self.__imframe.columnconfigure(0, weight=1)

    # noinspection PyUnusedLocal
    def __scroll_x(self, *args, **kwargs):
        """ Scroll canvas horizontally and redraw the image """
        self.canvas.xview(*args)  # scroll horizontally
        self.__show_image()  # redraw the image

    # noinspection PyUnusedLocal
    def __scroll_y(self, *args, **kwargs):
        """ Scroll canvas vertically and redraw the image """
        self.canvas.yview(*args)  # scroll vertically
        self.__show_image()  # redraw the image

    def __show_image(self):
        """ Show image on the Canvas. Implements correct image zoom almost like in Google Maps """
        box_image = self.canvas.coords(self.container)  # get image area
        box_canvas = (self.canvas.canvasx(0),  # get visible area of the canvas
                      self.canvas.canvasy(0),
                      self.canvas.canvasx(self.canvas.winfo_width()),
                      self.canvas.canvasy(self.canvas.winfo_height()))
        box_img_int = tuple(map(int, box_image))  # convert to integer or it will not work properly
        # Get scroll region box
        box_scroll = [min(box_img_int[0], box_canvas[0]), min(box_img_int[1], box_canvas[1]),
                      max(box_img_int[2], box_canvas[2]), max(box_img_int[3], box_canvas[3])]
        # Horizontal part of the image is in the visible area
        if  box_scroll[0] == box_canvas[0] and box_scroll[2] == box_canvas[2]:
            box_scroll[0]  = box_img_int[0]
            box_scroll[2]  = box_img_int[2]
        # Vertical part of the image is in the visible area
        if  box_scroll[1] == box_canvas[1] and box_scroll[3] == box_canvas[3]:
            box_scroll[1]  = box_img_int[1]
            box_scroll[3]  = box_img_int[3]
        # Convert scroll region to tuple and to integer
        self.canvas.configure(scrollregion=tuple(map(int, box_scroll)))  # set scroll region
        x1 = max(box_canvas[0] - box_image[0], 0)  # get coordinates (x1,y1,x2,y2) of the image tile
        y1 = max(box_canvas[1] - box_image[1], 0)
        x2 = min(box_canvas[2], box_image[2]) - box_image[0]
        y2 = min(box_canvas[3], box_image[3]) - box_image[1]
        if int(x2 - x1) > 0 and int(y2 - y1) > 0:  # show image if it in the visible area
            if self.__huge and self.__curr_img < 0:  # show huge image
                h = int((y2 - y1) / self.imscale)  # height of the tile band
                self.__tile[1][3] = h  # set the tile band height
                self.__tile[2] = self.__offset + self.imwidth * int(y1 / self.imscale) * 3
                self.__image.close()
                self.__image = Image.open(self.path)  # reopen / reset image
                self.__image.size = (self.imwidth, h)  # set size of the tile band
                self.__image.tile = [self.__tile]
                image = self.__image.crop((int(x1 / self.imscale), 0, int(x2 / self.imscale), h))
            else:  # show normal image
                image = self.__pyramid[max(0, self.__curr_img)].crop(  # crop current img from pyramid
                                    (int(x1 / self.__scale), int(y1 / self.__scale),
                                     int(x2 / self.__scale), int(y2 / self.__scale)))
            #
            imagetk = ImageTk.PhotoImage(image.resize((int(x2 - x1), int(y2 - y1)), self.__filter))
            imageid = self.canvas.create_image(max(box_canvas[0], box_img_int[0]),
                                               max(box_canvas[1], box_img_int[1]),
                                               anchor='nw', image=imagetk)
            self.canvas.lower(imageid)  # set image into background
            self.canvas.imagetk = imagetk  # keep an extra reference to prevent garbage-collection

    def __move_from(self, event):
        """ Remember previous coordinates for scrolling with the mouse """
        print(self.parent_container.label_mode.get())
        if self.parent_container.label_mode.get():
            self.cursorlocations = [[self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)]]
            box_image = self.canvas.coords(self.container)  # get image area
            x_scale = (box_image[2] - box_image[0])/self.imwidth
            y_scale = (box_image[3] - box_image[1])/self.imheight
            self.locations = [[(self.canvas.canvasx(event.x) - box_image[0])/x_scale, (self.canvas.canvasy(event.y) - box_image[1])/y_scale]]
        else:
            self.canvas.scan_mark(event.x, event.y)

    def __move_to(self, event):
        """ Drag (move) canvas to the new position """
        if self.parent_container.label_mode.get():
            box_image = self.canvas.coords(self.container)  # get image area
            x_scale = (box_image[2] - box_image[0])/self.imwidth
            y_scale = (box_image[3] - box_image[1])/self.imheight
            self.cursorlocations.append([self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)])
            self.locations.append([(self.canvas.canvasx(event.x) - box_image[0])/x_scale, (self.canvas.canvasy(event.y) - box_image[1])/y_scale])
        else:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
            self.__show_image()  # zoom tile and show it on the canvas

    def __on_release(self, event):
        if self.parent_container.label_mode.get():
            first = self.cursorlocations[0]
            last = self.cursorlocations[-1]
            print("drawing...")
            rect = self.canvas.create_rectangle(first[0], first[1], last[0], last[1], outline="green2")
            rect_text = self.canvas.create_text(min(first[0], last[0]), min(first[1], last[1]), text=self.parent_container.label_type.get(), fill="green2")
            first = self.locations[0]
            last = self.locations[-1]
            new_label = Label(first[0], first[1], last[0], last[1], self.parent_container.label_type.get(), rect, rect_text)
            self.parent_container.labels_created.append(
                new_label
            )
            self.parent_container.create_label(new_label)

    def outside(self, x, y):
        """ Checks if the point (x,y) is outside the image area """
        bbox = self.canvas.coords(self.container)  # get image area
        if bbox[0] < x < bbox[2] and bbox[1] < y < bbox[3]:
            return False  # point (x,y) is inside the image area
        else:
            return True  # point (x,y) is outside the image area

    def __wheel(self, event):
        """ Zoom with mouse wheel """
        x = self.canvas.canvasx(event.x)  # get coordinates of the event on the canvas
        y = self.canvas.canvasy(event.y)
        if self.outside(x, y): return  # zoom only inside image area
        scale = 1.0
        # Respond to Linux (event.num) or Windows (event.delta) wheel event
        if event.num == 5 or event.delta == -120:  # scroll down, smaller
            if round(self.__min_side * self.imscale) < 30: return  # image is less than 30 pixels
            self.imscale /= self.__delta
            scale        /= self.__delta
        if event.num == 4 or event.delta == 120:  # scroll up, bigger
            i = min(self.canvas.winfo_width(), self.canvas.winfo_height()) >> 1
            if i < self.imscale: return  # 1 pixel is bigger than the visible area
            self.imscale *= self.__delta
            scale        *= self.__delta
        # Take appropriate image from the pyramid
        k = self.imscale * self.__ratio  # temporary coefficient
        self.__curr_img = min((-1) * int(math.log(k, self.__reduction)), len(self.__pyramid) - 1)
        self.__scale = k * math.pow(self.__reduction, max(0, self.__curr_img))
        #
        self.canvas.scale('all', x, y, scale, scale)  # rescale all objects
        # Redraw some figures before showing image on the screen
        self.redraw_figures()  # method for child classes
        self.__show_image()
        print(self.__scale)

    def __keystroke(self, event):
        """ Scrolling with the keyboard.
            Independent from the language of the keyboard, CapsLock, <Ctrl>+<key>, etc. """
        if event.state - self.__previous_state == 4:  # means that the Control key is pressed
            pass  # do nothing if Control key is pressed
        else:
            self.__previous_state = event.state  # remember the last keystroke state
            # Up, Down, Left, Right keystrokes
            if event.keycode in [68, 39, 102]:  # scroll right: keys 'D', 'Right' or 'Numpad-6'
                self.__scroll_x('scroll',  1, 'unit', event=event)
            elif event.keycode in [65, 37, 100]:  # scroll left: keys 'A', 'Left' or 'Numpad-4'
                self.__scroll_x('scroll', -1, 'unit', event=event)
            elif event.keycode in [87, 38, 104]:  # scroll up: keys 'W', 'Up' or 'Numpad-8'
                self.__scroll_y('scroll', -1, 'unit', event=event)
            elif event.keycode in [83, 40, 98]:  # scroll down: keys 'S', 'Down' or 'Numpad-2'
                self.__scroll_y('scroll',  1, 'unit', event=event)

    def crop(self, bbox):
        """ Crop rectangle from the image and return it """
        if self.__huge:  # image is huge and not totally in RAM
            band = bbox[3] - bbox[1]  # width of the tile band
            self.__tile[1][3] = band  # set the tile height
            self.__tile[2] = self.__offset + self.imwidth * bbox[1] * 3  # set offset of the band
            self.__image.close()
            self.__image = Image.open(self.path)  # reopen / reset image
            self.__image.size = (self.imwidth, band)  # set size of the tile band
            self.__image.tile = [self.__tile]
            return self.__image.crop((bbox[0], 0, bbox[2], band))
        else:  # image is totally in RAM
            return self.__pyramid[0].crop(bbox)

    def destroy(self):
        """ ImageFrame destructor """
        self.__image.close()
        map(lambda i: i.close, self.__pyramid)  # close all pyramid images
        del self.__pyramid[:]  # delete pyramid list
        del self.__pyramid  # delete pyramid variable
        self.canvas.destroy()
        self.__imframe.destroy()

class Label():
    def __init__(self, x, y, x1, y1, label_type, rectangle_drawn=None, text_drawn=None):
        self.x = x
        self.y = y
        self.x1 = x1
        self.y1 = y1
        self.type = label_type
        self.rectangle_drawn = rectangle_drawn
        self.text_drawn = text_drawn

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.label_type = tk.StringVar()
        self.label_type.set("Redact")
        self.label_mode = tk.BooleanVar()
        self.label_mode.set(False)
        self.label_options = ["Redact_Blur", "Redact_Blur", "Redact_Blur_Text", "Ticker", "Account_Name", "Value", "Curr_Ticker", "Date"]
        self.labels_created = []
        self.files = [i for i in glob.glob("templates/*") if os.path.splitext(i)[1] in [".png", ".jpg", ".tif"]]
        print(self.files)
        self.file_name = tk.StringVar()
        if self.files != []:
            self.files.insert(0, self.files[0])
            self.file_name.set(self.files[0])
        self.__create_widgets()

    def __create_widgets(self):
        self.read_labels()
        self.columnconfigure(index=0, weight=1)
        self.rowconfigure(index=0, weight=1)

        self.canvas_image = CanvasImage(self, self.file_name.get())
        self.canvas_image.grid(column=0, row=0)

        self.button_frame = CanvasButtonFrame(self)
        self.button_frame.grid(column=0, row=1)

        self.label_frame = LabelsFrame(self)
        self.label_frame.grid(column=1, row=0)
        self.add_existing_labels()

        label_button_frame = LabelButtonFrame(self)
        label_button_frame.grid(column=1, row=1)

        self.bin_frame = BinsFrame(self)
        self.bin_frame.grid(column=2, row=0)

        bin_button_frame = BinButtonFrame(self, self.bin_frame)
        bin_button_frame.grid(column=2, row=1)

    def label_mode_off(self):
        self.button_frame.label_button["state"] = "enabled"
        self.button_frame.nav_button["state"] = "disabled"
        self.label_mode.set(False)

    def label_mode_on(self):
        self.button_frame.nav_button["state"] = "enabled"
        self.button_frame.label_button["state"] = "disabled"
        self.label_mode.set(True)

    def create_label(self, label):
        self.label_frame.add_label(label)

    def highlight(self, label_rectangle):
        self.canvas_image.canvas.itemconfig(label_rectangle, width='3')
        self.canvas_image.canvas.itemconfig(label_rectangle, width='3')

    def unhighlight(self, label_rectangle):
        self.canvas_image.canvas.itemconfig(label_rectangle, width='1')

    def send_label_to_bin(self, label, label_id):
        self.bin_frame.add_label(label)
        self.unhighlight(label.rectangle_drawn)
        label_id.destroy()

    def retrieve_label_from_bin(self, label, label_id):
        self.label_frame.add_label(label)
        self.unhighlight(label.rectangle_drawn)
        label_id.destroy()

    def read_labels(self):
        extension = self.file_name.get().split(".")[-1]
        text_file_name = self.file_name.get().replace(f".{extension}", ".txt")
        if os.path.exists(text_file_name):
            with open(text_file_name, "r") as f:
                labels = f.readlines()
            self.labels_created = []
            for label in labels:
                i = label.strip().split(" ")
                self.labels_created.append(Label(float(i[1]), float(i[2]), float(i[3]), float(i[4]), i[0]))
            print(self.labels_created)
        else:
            self.labels_created = []

    def add_existing_labels(self):
        for label in self.labels_created:
            self.create_label(label)

    def export(self):
        print(self.file_name.get())
        extension = self.file_name.get().split(".")[-1]
        text_file_name = self.file_name.get().replace(f".{extension}", ".txt")
        with open(text_file_name, "w") as f:
            for label in self.labels_created:
                string = f"{label.type} {label.x} {label.y} {label.x1} {label.y1}\n"
                f.write(string)
        print(f"Written to file {text_file_name}")

    def change_img(self, value):
        self.__create_widgets()
        self.file_name.set(value)
        print(value)

class CanvasButtonFrame(ttk.Frame):
    def __init__(self, container):
        super().__init__(container)
        self.__create_widgets(container)

    def __create_widgets(self, container):
        ttk.Button(self, text="<").grid(column=0, row=0)
        ttk.OptionMenu(self, container.file_name, *container.files, command=container.change_img).grid(column=1, row=0)
        # ttk.Label(self, text="Some text here...").grid(column=1, row=0)
        ttk.Button(self, text=">").grid(column=2, row=0)
        self.label_button = ttk.Button(self, text="Label Mode", command=container.label_mode_on, state="enabled")
        self.label_button.grid(column=3, row=0)
        self.nav_button = ttk.Button(self, text="Navigate Mode", command=container.label_mode_off, state="disabled")
        self.nav_button.grid(column=4, row=0)
        self.export_button = ttk.Button(self, text="Export", command=container.export)
        self.export_button.grid(column=5, row=0)

        for widget in self.winfo_children():
            widget.grid(padx=0, pady=0)

class LabelsFrame(ttk.Frame):
    def __init__(self, container):
        super().__init__(container)
        self.container = container
        self.__create_widgets()
        self.labels = []

    def __create_widgets(self):
        self.frame = ttk.LabelFrame(self, text="Labels", borderwidth=2, border=2)
        self.frame.grid(column=0, row=0, sticky="NEWS")

    def add_label(self, label):
        self.label = ttk.Label(self.frame, text=label.type)
        self.label.bind('<Enter>', lambda event, id = label.rectangle_drawn: self.container.highlight(id))
        self.label.bind('<Leave>', lambda event, id = label.rectangle_drawn: self.container.unhighlight(id))
        self.label.bind('<1>', lambda event, id = label, label_id = self.label: self.container.send_label_to_bin(label, label_id))
        self.label.pack()

class LabelButtonFrame(ttk.Frame):
    def __init__(self, container):
        self.label_type = container.label_type
        self.label_options = container.label_options
        super().__init__(container)
        self.__create_widgets()

    def __create_widgets(self):
        ttk.OptionMenu(self, self.label_type, *self.label_options)
        for widget in self.winfo_children():
            widget.grid(padx=0, pady=0)

class BinsFrame(ttk.Frame):
    def __init__(self, container):
        super().__init__(container)
        self.container = container
        self.__create_widgets()
        self.labels = []
        self.label_widgets = []

    def __create_widgets(self):
        self.frame = ttk.LabelFrame(self, text="Bins", borderwidth=2, border=2)
        self.frame.grid(column=0, row=0, sticky="NEWS")

    def add_label(self, label):
        self.labels.append(label)
        self.label = ttk.Label(self.frame, text=label.type)
        self.label.bind('<Enter>', lambda event, id = label.rectangle_drawn: self.container.highlight(id))
        self.label.bind('<Leave>', lambda event, id = label.rectangle_drawn: self.container.unhighlight(id))
        self.label.bind('<1>', lambda event, id = label, label_id = self.label: self.container.retrieve_label_from_bin(label, label_id))
        self.label_widgets.append(self.label)
        self.label.pack()

    def empty_bin(self):
        print(self.container.labels_created)
        for label_widget in self.label_widgets:
            label_widget.destroy()
        for label in self.labels:
            self.container.canvas_image.canvas.delete(label.rectangle_drawn)
            self.container.canvas_image.canvas.delete(label.text_drawn)
            self.container.labels_created.remove(label)
        self.labels = []
        print(self.container.labels_created)

class BinButtonFrame(ttk.Frame):
    def __init__(self, container, bin_frame):
        super().__init__(container)
        self.bin_frame = bin_frame
        self.__create_widgets()

    def __create_widgets(self):
        ttk.Button(self, text="Delete", command=self.bin_frame.empty_bin).grid(column=0, row=0)

        for widget in self.winfo_children():
            widget.grid(padx=0, pady=0)

if __name__ == "__main__":
    app = App()
    app.mainloop()

